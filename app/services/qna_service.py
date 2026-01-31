import os
import pandas as pd
import numpy as np
from flask import current_app
from datetime import datetime
import re
import google.generativeai as genai
import spacy

class QnAService:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or current_app.config.get('DATABASE_PATH', 'campusiq.db')
        try:
            self.nlp = spacy.blank("en")
        except:
            self.nlp = None

    def _get_timetable_data(self, college_id):
        """Fetch all timetable entries for the college"""
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            query = """
                SELECT day_of_week, start_time, end_time, class_code, 
                       subject_name, instructor_name, room_code
                FROM schedules 
                WHERE college_id = ? AND is_deleted = 0
            """
            df = pd.read_sql_query(query, conn, params=[college_id])
            conn.close()
            
            if df.empty: return None
            
            days = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}
            df['day_name'] = df['day_of_week'].map(days)
            return df
        except Exception as e:
            current_app.logger.error(f"Error loading timetable: {e}")
            return None

    def _get_user_name(self, user_id):
        """Get the full name of the user to match against instructor names"""
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT full_name FROM users WHERE user_id = ?", (user_id,))
            res = cursor.fetchone()
            conn.close()
            return res[0] if res else None
        except: return None

    # === STEP 1: QUERY UNDERSTANDING ===
    def _understand_query(self, query):
        """
        Processes raw text to extract intent, entities, and temporal context.
        """
        query_lower = query.lower().strip()
        entities = {
            'days': [],
            'rooms': [],
            'faculty': [],
            'classes': [],
            'subjects': [],
            'personal': any(w in query_lower for w in ['my class', 'my schedule', 'subjects i teach', 'i teach']),
            'intent': 'academic_search'
        }

        # Intent detection
        if any(w in query_lower for w in ['free room', 'empty room', 'vacant room', 'available room']):
            entities['intent'] = 'free_rooms'

        # Temporal Detection
        if 'next' in query_lower: entities['relative_time'] = 'next'
        elif any(w in query_lower for w in ['current', 'now', 'right now']): entities['relative_time'] = 'current'
        elif 'tomorrow' in query_lower: entities['relative_time'] = 'tomorrow'
        
        # Specific Time Detection (e.g., 03:30 PM)
        time_match = re.search(r'(\d{1,2})[:.]?(\d{2})?\s?(am|pm)', query_lower)
        if time_match:
            h = int(time_match.group(1))
            m = int(time_match.group(2)) if time_match.group(2) else 0
            if time_match.group(3) == 'pm' and h < 12: h += 12
            if time_match.group(3) == 'am' and h == 12: h = 0
            entities['time'] = h * 60 + m

        # Day Detection
        days_map = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
        for d, idx in days_map.items():
            if d in query_lower: entities['days'].append(idx)
        
        # Room Detection
        room_matches = re.findall(r'[a-z]-\d{3}[a-z]?', query_lower)
        entities['rooms'] = [r.upper() for r in room_matches]

        # Year/Branch Detection (SE IT, FE COMP, etc)
        acad_matches = re.findall(r'\b(fe|se|ty|be|sy)\s+(it|comp|ecs|extc|mech|civil|auto)\b', query_lower)
        for year, branch in acad_matches:
            entities['classes'].append(f"{year.upper()} {branch.upper()}")

        return entities

    # === STEP 2: SEMANTIC SEARCH & FILTERING ===
    def _semantic_filter(self, df, query, entities, user_name=None):
        if df is None: return []

        now = datetime.now()
        target_day = now.weekday()
        if entities['relative_time'] == 'tomorrow':
            target_day = (target_day + 1) % 7
        elif entities['days']:
            target_day = entities['days'][0]

        now_min = now.hour * 60 + now.minute
        if entities['time'] is not None:
            now_min = entities['time']

        # Start with Day filtering - but if personal query and no day mentioned, search WHOLE week
        is_personal_query = entities['personal'] or any(w in query.lower() for w in ['my', 'me', 'i teach'])
        
        has_day_mentioned = entities['days'] or entities['relative_time']
        
        if is_personal_query and not has_day_mentioned:
            # Fallback to whole week
            filtered_df = df.copy()
        else:
            filtered_df = df[df['day_of_week'] == target_day].copy()

        # Personal filter logic
        if is_personal_query and user_name:
            # Partial match for names (handles "Anjali" matching "Anjali Nambiar")
            filtered_df = filtered_df[filtered_df['instructor_name'].str.contains(user_name.split()[0], case=False, na=False)]
        
        # If the dataframe became empty after personal filter (and it was a personal query), 
        # that means we have NO records for this user today.
        if filtered_df.empty and is_personal_query:
            return []

        # Apply temporal logic
        if entities['relative_time'] == 'current':
            matches = []
            for _, row in filtered_df.iterrows():
                try:
                    s = self._parse_time_min(row['start_time'])
                    e = self._parse_time_min(row['end_time'])
                    if s <= now_min < e: matches.append(dict(row))
                except: continue
            if matches: return matches
        
        elif entities['relative_time'] == 'next':
            filtered_df['start_min'] = filtered_df['start_time'].apply(self._parse_time_min)
            next_classes = filtered_df[filtered_df['start_min'] >= now_min].sort_values('start_min')
            if not next_classes.empty: return next_classes.head(3).to_dict('records')

        # Generic Semantic Weighting
        scores = np.zeros(len(filtered_df))
        # Filter out common stop words that don't help in DB record matching
        stop_words = {'show', 'me', 'the', 'what', 'is', 'when', 'today', 'tomorrow', 'schedule', 'table', 'tell'}
        query_words = [w for w in query.lower().split() if w not in stop_words and len(w) > 1]
        
        filtered_df = filtered_df.reset_index(drop=True)
        
        # IF NO SPECIFIC KEYWORDS after filtering stop words, but it's a "Today" or "Tomorrow" query
        # Just return the first few classes of that day
        if not query_words and not filtered_df.empty:
            return filtered_df.head(5).to_dict('records')

        for i, row in filtered_df.iterrows():
            row_str = f"{row['class_code']} {row['subject_name']} {row['instructor_name']} {row['room_code']}".lower()
            
            # Boost if specific room or class matched in entities
            if row['room_code'] in entities['rooms']: scores[i] += 20
            if any(c in row['class_code'].upper() for c in entities['classes']): scores[i] += 15
            
            # Keyword match
            for word in query_words:
                if word in row_str:
                    scores[i] += 5
                    # Exact word match boost
                    if word in row_str.split(): scores[i] += 5

        top_indices = np.argsort(scores)[-5:][::-1]
        results = []
        for idx in top_indices:
            if scores[idx] > 0: results.append(filtered_df.iloc[idx].to_dict())
        
        # Final fallback: if still nothing but we have day data, show summary
        if not results and not filtered_df.empty and (entities['days'] or entities['relative_time']):
             return filtered_df.head(3).to_dict('records')

        return results

    def _parse_time_min(self, t_str):
        try:
            t_str = t_str.upper().strip()
            is_pm = 'PM' in t_str
            is_am = 'AM' in t_str
            clean = re.sub(r'[APM\s]', '', t_str)
            parts = clean.split(':')
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            if is_pm and h < 12: h += 12
            if is_am and h == 12: h = 0
            # Heuristic for 24h formatted without PM/AM
            if not is_am and not is_pm and h < 8: h += 12 
            return h * 60 + m
        except: return 0

    def _format_no_markdown(self, results, entities=None):
        """
        Formats results clearly with no bolding (**) or complex markdown.
        """
        if not results:
            return "I don’t have enough verified information to answer this."

        response = "RECORDS RETRIEVED FROM DATABASE:\n\n"
        for i, res in enumerate(results[:5], 1):
            response += f"ITEM {i}:\n"
            response += f"- Day: {res.get('day_name', 'Unknown')}\n"
            response += f"- Time: {res.get('start_time')} to {res.get('end_time')}\n"
            response += f"- Class: {res.get('class_code')}\n"
            response += f"- Subject: {res.get('subject_name')}\n"
            response += f"- Room: {res.get('room_code')}\n"
            response += f"- Teacher: {res.get('instructor_name')}\n\n"
        return response

    # === STEP 3: RELEVANT Q&A RETRIEVED (TEXT FORMATTER) ===
    # === STEP 3: GENERATIVE AI (GEMINI) ===
    def _generate_ai_response(self, query, results, user_name=None):
        """
        Uses Gemini to generate a response based on the retrieved database context.
        """
        api_key = current_app.config.get('GEMINI_API_KEY')
        model_name = current_app.config.get('GEMINI_MODEL', 'gemini-2.0-flash')

        if not api_key:
            return self._format_no_markdown(results, {})

        try:
            # Re-configure only if needed or just use global
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)

            context = ""
            if results:
                context = "DATABASE RECORDS FOUND:\n"
                for i, r in enumerate(results, 1):
                    # Use .get() for safety
                    c_code = r.get('class_code', 'Unknown')
                    s_name = r.get('subject_name', 'Unknown')
                    i_name = r.get('instructor_name', 'Unknown')
                    r_code = r.get('room_code', 'Unknown')
                    context += f"- {r.get('day_name')} {r.get('start_time')}-{r.get('end_time')}: {s_name} for {c_code} with {i_name} in Room {r_code}\n"
            else:
                context = "No matching records found in the database. Please inform the user that no records exist for their query."

            prompt = f"""
            You are an availability assistant for CampusIQ (Pillai College of Engineering).
            
            Current Context: {datetime.now().strftime('%A, %H:%M')}
            USER IDENTITY: {user_name or 'Faculty Member'}
            USER QUESTION: "{query}"

            {context}

            YOUR RESPONSIBILITIES:
            1. Identify the entity type requested (faculty, room, lab, or other).
            2. Identify the day and time range from the user query.
            3. Format results using ONLY the provided availability data (database records).

            RULES:
            - Do NOT guess or invent availability.
            - Do NOT repeat entities.
            - Always include entity name and available time.
            - If nothing is available, clearly state that.
            - Keep the response professional and under 4-5 lines.
            - Use plain text only (no bolding, no markdown).

            RESPONSE:
            """
            
            response = model.generate_content(prompt)
            
            if not response or not response.text:
                return self._format_no_markdown(results)
                
            return response.text.replace('**', '').replace('###', '').strip()

        except Exception as e:
            current_app.logger.error(f"Gemini AI Error: {e}")
            return self._format_no_markdown(results)

    def process_query(self, query, college_id=None, user_id=None, user_role=None):
        start_time_proc = datetime.now()
        
        # 1. Pipeline: Understanding
        entities = self._understand_query(query)
        user_name = self._get_user_name(user_id) if user_id else None
        
        # 2. Pipeline: Data Retrieval & Filter
        df = self._get_timetable_data(college_id)
        
        search_results = []
        if entities['intent'] == 'free_rooms':
            search_results = self._handle_free_rooms(college_id, entities)
        else:
            search_results = self._semantic_filter(df, query, entities, user_name)
        
        # 3. Pipeline: AI Generation (RAG)
        response = self._generate_ai_response(query, search_results, user_name)
        
        processing_time = (datetime.now() - start_time_proc).total_seconds() * 1000

        return {
            'intent': entities['intent'],
            'response': response,
            'response_type': 'text',
            'results': search_results if entities['intent'] != 'free_rooms' else [],
            'processing_time_ms': int(processing_time)
        }

    def _handle_free_rooms(self, college_id, entities):
        """Logic to calculate free rooms now"""
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            
            # Get all rooms
            cursor = conn.cursor()
            cursor.execute("SELECT room_code FROM rooms WHERE college_id = ? AND is_deleted = 0", (college_id,))
            all_rooms = {row[0] for row in cursor.fetchall()}
            
            # Get busy rooms now
            now = datetime.now()
            target_day = now.weekday()
            now_min = now.hour * 60 + now.minute
            
            cursor.execute("""
                SELECT room_code, start_time, end_time FROM schedules 
                WHERE college_id = ? AND day_of_week = ? AND is_deleted = 0
            """, (college_id, target_day))
            
            busy_rooms = set()
            for room, start, end in cursor.fetchall():
                try:
                    s = self._parse_time_min(start)
                    e = self._parse_time_min(end)
                    if s <= now_min < e:
                        busy_rooms.add(room)
                except: continue
                
            free_rooms = list(all_rooms - busy_rooms)
            conn.close()
            
            return [{ 'room_code': r, 'day_name': 'Today', 'subject_name': 'FREE' } for r in sorted(free_rooms)[:15]]
        except Exception as e:
            current_app.logger.error(f"Free Room Error: {e}")
            return []

    def get_user_history(self, **kwargs): return []
    def submit_feedback(self, **kwargs): pass
    def get_insights(self, **kwargs): return {}
