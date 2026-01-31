import os
import re
import google.generativeai as genai
from flask import current_app, g
from datetime import datetime
from sqlalchemy import text


class QnAService:
    """Service for AI-powered Q&A and timetable insights"""
    
    def __init__(self, db_path: str = None):
        pass # Not needed for SQLAlchemy

    def _get_timetable_data(self, college_id):
        """Fetch all timetable entries for the college"""
        try:
            db = current_app.extensions['sqlalchemy']
            query = text("""
                SELECT day_of_week, start_time, end_time, class_code, 
                       subject_name, instructor_name, room_code
                FROM schedules 
                WHERE college_id = :college_id AND is_deleted = 0
            """)
            
            with db.engine.connect() as conn:
                result = conn.execute(query, {"college_id": college_id})
                rows = [dict(row._mapping) for row in result]
            
            days = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}
            for row in rows:
                row['day_name'] = days.get(row['day_of_week'])
            
            return rows
        except Exception as e:
            current_app.logger.error(f"Error loading timetable: {e}")
            return []

    def _get_user_name(self, user_id):
        """Get the full name of the user"""
        try:
            db = current_app.extensions['sqlalchemy']
            with db.engine.connect() as conn:
                result = conn.execute(text("SELECT full_name FROM users WHERE user_id = :uid"), {"uid": user_id}).fetchone()
                return result[0] if result else None
        except:
            return None

    # === STEP 1: QUERY UNDERSTANDING ===
    def _understand_query(self, query):
        """Processes raw text to extract intent, entities, and temporal context."""
        query_lower = query.lower().strip()
        entities = {
            'days': [], 'rooms': [], 'faculty': [], 'classes': [], 'subjects': [],
            'personal': any(w in query_lower for w in ['my class', 'my schedule', 'subjects i teach', 'i teach']),
            'intent': 'academic_search'
        }

        if any(w in query_lower for w in ['free room', 'empty room', 'vacant room', 'available room']):
            entities['intent'] = 'free_rooms'

        if 'next' in query_lower: entities['relative_time'] = 'next'
        elif any(w in query_lower for w in ['current', 'now', 'right now']): entities['relative_time'] = 'current'
        elif 'tomorrow' in query_lower: entities['relative_time'] = 'tomorrow'
        else: entities['relative_time'] = None

        time_match = re.search(r'(\d{1,2})[:.]?(\d{2})?\s?(am|pm)', query_lower)
        if time_match:
            h = int(time_match.group(1))
            m = int(time_match.group(2)) if time_match.group(2) else 0
            if time_match.group(3) == 'pm' and h < 12: h += 12
            if time_match.group(3) == 'am' and h == 12: h = 0
            entities['time'] = h * 60 + m
        else:
            entities['time'] = None

        days_map = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
        for d, idx in days_map.items():
            if d in query_lower: entities['days'].append(idx)
        
        room_matches = re.findall(r'[a-z]-\d{3}[a-z]?', query_lower)
        entities['rooms'] = [r.upper() for r in room_matches]

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

        is_personal_query = entities['personal'] or any(w in query.lower() for w in ['my', 'me', 'i teach'])
        has_day_mentioned = entities['days'] or entities['relative_time']
        
        filtered_rows = rows if (is_personal_query and not has_day_mentioned) else [r for r in rows if r['day_of_week'] == target_day]

        if is_personal_query and user_name:
            u_name_part = user_name.split()[0].lower()
            filtered_rows = [r for r in filtered_rows if u_name_part in (r.get('instructor_name') or '').lower()]
        
        if not filtered_rows and is_personal_query: return []

        if entities['relative_time'] == 'current':
            matches = []
            for row in filtered_rows:
                try:
                    s, e = self._parse_time_min(row['start_time']), self._parse_time_min(row['end_time'])
                    if s <= now_min < e: matches.append(row)
                except: continue
            if matches: return matches
        
        elif entities['relative_time'] == 'next':
            next_classes = []
            for row in filtered_rows:
                 s = self._parse_time_min(row['start_time'])
                 if s >= now_min:
                     r = row.copy()
                     r['_start_min'] = s
                     next_classes.append(r)
            next_classes.sort(key=lambda x: x['_start_min'])
            return [{k: v for k, v in r.items() if k != '_start_min'} for r in next_classes[:3]]

        stop_words = {'show', 'me', 'the', 'what', 'is', 'when', 'today', 'tomorrow', 'schedule', 'table', 'tell'}
        query_words = [w for w in query.lower().split() if w not in stop_words and len(w) > 1]
        
        if not query_words: return filtered_rows[:5]

        scored_rows = []
        for row in filtered_rows:
            score = 0
            row_str = f"{row.get('class_code','')} {row.get('subject_name','')} {row.get('instructor_name','')} {row.get('room_code','')}".lower()
            if row.get('room_code') in entities['rooms']: score += 20
            if any(c in str(row.get('class_code','')).upper() for c in entities['classes']): score += 15
            for word in query_words:
                if word in row_str:
                    score += 5
                    if word in row_str.split(): score += 5
            if score > 0: scored_rows.append((score, row))

        scored_rows.sort(key=lambda x: x[0], reverse=True)
        results = [x[1] for x in scored_rows[:5]]
        return results if results or not (entities['days'] or entities['relative_time']) else filtered_rows[:3]

    def _parse_time_min(self, t_str):
        try:
            if not t_str: return 0
            t_str = t_str.upper().strip()
            is_pm, is_am = 'PM' in t_str, 'AM' in t_str
            clean = re.sub(r'[APM\s]', '', t_str)
            parts = clean.split(':')
            h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
            if is_pm and h < 12: h += 12
            if is_am and h == 12: h = 0
            if not is_am and not is_pm and h < 8: h += 12 
            return h * 60 + m
        except: return 0

    def _format_no_markdown(self, results, entities=None):
        if not results: return "I don’t have enough verified information to answer this."
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
        api_key = current_app.config.get('GEMINI_API_KEY')
        model_name = current_app.config.get('GEMINI_MODEL', 'gemini-2.0-flash')
        if not api_key: return self._format_no_markdown(results)

        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)
            context = "DATABASE RECORDS FOUND:\n" + "\n".join([
                f"- {r.get('day_name')} {r.get('start_time')}-{r.get('end_time')}: {r.get('subject_name')} for {r.get('class_code')} with {r.get('instructor_name')} in Room {r.get('room_code')}"
                for r in results
            ]) if results else "No matching records found."

            prompt = f"Assistant for CampusIQ. Context: {datetime.now().strftime('%A, %H:%M')}. User: {user_name or 'Faculty'}. Query: {query}.\n{context}\nRule: Use plain text only, no bold/markdown, max 4 lines. Respond based on data strictly."
            response = model.generate_content(prompt)
            return response.text.replace('**', '').replace('###', '').strip() if response and response.text else self._format_no_markdown(results)
        except Exception as e:
            current_app.logger.error(f"Gemini AI Error: {e}")
            return self._format_no_markdown(results)

    def process_query(self, query, college_id=None, user_id=None, user_role=None):
        start = datetime.now()
        entities = self._understand_query(query)
        user_name = self._get_user_name(user_id)
        rows = self._get_timetable_data(college_id)
        
        search_results = self._handle_free_rooms(college_id, entities) if entities['intent'] == 'free_rooms' else self._semantic_filter(rows, query, entities, user_name)
        response = self._generate_ai_response(query, search_results, user_name)
        
        return {
            'intent': entities['intent'], 'response': response, 'response_type': 'text',
            'results': search_results if entities['intent'] != 'free_rooms' else [],
            'processing_time_ms': int((datetime.now() - start).total_seconds() * 1000)
        }

    def _handle_free_rooms(self, college_id, entities):
        try:
            db = current_app.extensions['sqlalchemy']
            with db.engine.connect() as conn:
                res_all = conn.execute(text("SELECT room_code FROM rooms WHERE college_id = :cid AND is_deleted = 0"), {"cid": college_id})
                all_rooms = {row._mapping['room_code'] for row in res_all}
                
                now = datetime.now()
                target_day, now_min = now.weekday(), now.hour * 60 + now.minute
                
                res_busy = conn.execute(text("SELECT room_code, start_time, end_time FROM schedules WHERE college_id = :cid AND day_of_week = :day AND is_deleted = 0"), {"cid": college_id, "day": target_day})
                
                busy_rooms = set()
                for row in res_busy:
                    m = row._mapping
                    try:
                        if self._parse_time_min(m['start_time']) <= now_min < self._parse_time_min(m['end_time']):
                            busy_rooms.add(m['room_code'])
                    except: continue
                free = sorted(list(all_rooms - busy_rooms))
            return [{'room_code': r, 'day_name': 'Today', 'subject_name': 'FREE'} for r in free[:15]]
        except Exception as e:
            current_app.logger.error(f"Free Room Error: {e}")
            return []

    def get_user_history(self, **kwargs): return []
    def submit_feedback(self, **kwargs): pass
    def get_insights(self, **kwargs): return {}
