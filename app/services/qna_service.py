import os
from flask import current_app, g
from datetime import datetime
import re
import google.generativeai as genai

class QnAService:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or current_app.config.get('DATABASE_PATH', 'campusiq.db')

    def _get_connection(self):
        """Helper to get DB connection based on environment"""
        # Checks if we should use SQLite or PostgreSQL logic happens at app level
        # For this service, we assume standard SQL query compatibility or simple logic
        # Ideally, we should use SQLAlchemy from flask app if possible, but keeping it simple for now
        # If using postgres, we might need a different connector or use the SQLAlchemy engine
        pass

    def _get_timetable_data(self, college_id):
        """Fetch all timetable entries for the college as list of dicts"""
        try:
            # Check if we are in Postgres mode (using SQLAlchemy engine usually provided in app)
            # But here we are using raw queries. Let's try to leverage the existing db setup if possible.
            # For simplicity in this "serverless size fix", let's assume we can get a connection.
            # In production (Postgres), invalidating 'sqlite3' import is good.
            
            # Using SQLAlchemy engine from current_app if available
            from sqlalchemy import text
            db = current_app.extensions.get('sqlalchemy')
            if not db:
                return []

            query = text("""
                SELECT day_of_week, start_time, end_time, class_code, 
                       subject_name, instructor_name, room_code
                FROM schedules 
                WHERE college_id = :college_id AND is_deleted = 0
            """)
            
            with db.engine.connect() as conn:
                result = conn.execute(query, {"college_id": college_id})
                rows = [dict(row._mapping) for row in result] # Convert Row to Dict
            
            days = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}
            for row in rows:
                row['day_name'] = days.get(row['day_of_week'])
            
            return rows

        except Exception as e:
            current_app.logger.error(f"Error loading timetable: {e}")
            return []

    def _get_user_name(self, user_id):
        """Get the full name of the user to match against instructor names"""
        try:
            from sqlalchemy import text
            db = current_app.extensions.get('sqlalchemy')
            if not db: return None

            query = text("SELECT full_name FROM users WHERE user_id = :user_id")
            with db.engine.connect() as conn:
                result = conn.execute(query, {"user_id": user_id}).fetchone()
                return result[0] if result else None
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
        else: entities['relative_time'] = None # Explicitly set None if not found
        
        # Specific Time Detection (e.g., 03:30 PM)
        time_match = re.search(r'(\d{1,2})[:.]?(\d{2})?\s?(am|pm)', query_lower)
        if time_match:
            h = int(time_match.group(1))
            m = int(time_match.group(2)) if time_match.group(2) else 0
            if time_match.group(3) == 'pm' and h < 12: h += 12
            if time_match.group(3) == 'am' and h == 12: h = 0
            entities['time'] = h * 60 + m
        else:
            entities['time'] = None

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
    def _semantic_filter(self, rows, query, entities, user_name=None):
        if not rows: return []

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
        
        filtered_rows = []
        if is_personal_query and not has_day_mentioned:
            filtered_rows = list(rows)
        else:
            filtered_rows = [r for r in rows if r['day_of_week'] == target_day]

        # Personal filter logic
        if is_personal_query and user_name:
            # Partial match for names
            u_name_part = user_name.split()[0].lower()
            filtered_rows = [r for r in filtered_rows if u_name_part in (r.get('instructor_name') or '').lower()]
        
        if not filtered_rows and is_personal_query:
            return []

        # Apply temporal logic
        if entities['relative_time'] == 'current':
            matches = []
            for row in filtered_rows:
                try:
                    s = self._parse_time_min(row['start_time'])
                    e = self._parse_time_min(row['end_time'])
                    if s <= now_min < e: matches.append(row)
                except: continue
            if matches: return matches
        
        elif entities['relative_time'] == 'next':
            next_classes = []
            for row in filtered_rows:
                 s = self._parse_time_min(row['start_time'])
                 if s >= now_min:
                     row['_start_min'] = s # Temp key for sorting
                     next_classes.append(row)
            
            # Sort by start time
            next_classes.sort(key=lambda x: x['_start_min'])
            
            # Remove temp key and return top 3
            result = []
            for r in next_classes[:3]:
                r_copy = r.copy()
                if '_start_min' in r_copy: del r_copy['_start_min']
                result.append(r_copy)
            
            if result: return result

        # Generic Semantic Weighting
        # Filter out common stop words
        stop_words = {'show', 'me', 'the', 'what', 'is', 'when', 'today', 'tomorrow', 'schedule', 'table', 'tell'}
        query_words = [w for w in query.lower().split() if w not in stop_words and len(w) > 1]
        
        # IF NO SPECIFIC KEYWORDS and simple time query, return first few
        if not query_words and len(filtered_rows) > 0:
            return filtered_rows[:5]

        scored_rows = []
        for row in filtered_rows:
            score = 0
            # Construct a string representation for searching
            row_str = f"{row.get('class_code','')} {row.get('subject_name','')} {row.get('instructor_name','')} {row.get('room_code','')}".lower()
            
            # Boost if specific entities matched
            if row.get('room_code') in entities['rooms']: score += 20
            if any(c in str(row.get('class_code','')).upper() for c in entities['classes']): score += 15
            
            # Keyword match
            for word in query_words:
                if word in row_str:
                    score += 5
                    # Exact word match boost
                    if word in row_str.split(): score += 5
            
            if score > 0:
                scored_rows.append((score, row))

        # Sort by score descending
        scored_rows.sort(key=lambda x: x[0], reverse=True)
        results = [x[1] for x in scored_rows[:5]]
        
        # Final fallback
        if not results and filtered_rows and (entities['days'] or entities['relative_time']):
             return filtered_rows[:3]

        return results

    def _parse_time_min(self, t_str):
        try:
            if not t_str: return 0
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
        rows = self._get_timetable_data(college_id)
        
        search_results = []
        if entities['intent'] == 'free_rooms':
            search_results = self._handle_free_rooms(college_id, entities)
        else:
            search_results = self._semantic_filter(rows, query, entities, user_name)
        
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
            from sqlalchemy import text
            db = current_app.extensions.get('sqlalchemy')
            if not db: return []
            
            # Get all rooms
            with db.engine.connect() as conn:
                res_all = conn.execute(text("SELECT room_code FROM rooms WHERE college_id = :cid AND is_deleted = 0"), {"cid": college_id})
                all_rooms = {row[0] for row in res_all}
                
                # Get busy rooms now
                now = datetime.now()
                target_day = now.weekday()
                now_min = now.hour * 60 + now.minute
                
                res_busy = conn.execute(text("""
                    SELECT room_code, start_time, end_time FROM schedules 
                    WHERE college_id = :cid AND day_of_week = :day AND is_deleted = 0
                """), {"cid": college_id, "day": target_day})
                
                busy_rooms = set()
                for row in res_busy:
                    # Access by index or name depending on driver
                    # SQLAlchemy Rows are tuple-like
                    r_code = row[0]
                    start = row[1]
                    end = row[2]
                    
                    try:
                        s = self._parse_time_min(start)
                        e = self._parse_time_min(end)
                        if s <= now_min < e:
                            busy_rooms.add(r_code)
                    except: continue
                    
                free_rooms = list(all_rooms - busy_rooms)
            
            return [{ 'room_code': r, 'day_name': 'Today', 'subject_name': 'FREE' } for r in sorted(free_rooms)[:15]]
        except Exception as e:
            current_app.logger.error(f"Free Room Error: {e}")
            return []

    def get_user_history(self, **kwargs): return []
    def submit_feedback(self, **kwargs): pass
    def get_insights(self, **kwargs): return {}
