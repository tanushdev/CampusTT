import os
import re
import uuid
import google.generativeai as genai
from flask import current_app, g
from datetime import datetime
from sqlalchemy import text


class QnAService:
    """Service for AI-powered Q&A and timetable insights"""
    
    def __init__(self, db_path: str = None):
        pass

    def _get_timetable_data(self, college_id):
        """Fetch all timetable entries for the college"""
        try:
            db = current_app.extensions['sqlalchemy']
            with db.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT day_of_week, start_time, end_time, class_code, 
                           subject_name, instructor_name, room_code
                    FROM schedules 
                    WHERE college_id = :cid AND is_deleted = 0
                """), {"cid": uuid.UUID(str(college_id))})
                rows = [dict(row._mapping) for row in result]
            
            days = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}
            for row in rows: row['day_name'] = days.get(row['day_of_week'])
            return rows
        except Exception as e:
            current_app.logger.error(f"QnA loader failed: {e}")
            return []

    def _get_user_name(self, user_id):
        try:
            if not user_id: return None
            db = current_app.extensions['sqlalchemy']
            with db.engine.connect() as conn:
                res = conn.execute(text("SELECT full_name FROM users WHERE user_id = :uid"), {"uid": uuid.UUID(str(user_id))}).fetchone()
                return res[0] if res else None
        except: return None

    def _understand_query(self, query):
        q = query.lower().strip()
        entities = {
            'days': [], 'rooms': [], 'classes': [], 'intent': 'academic_search', 'relative_time': None, 'time': None,
            'personal': any(w in q for w in ['my class', 'my schedule', 'subjects i teach', 'i teach'])
        }
        if any(w in q for w in ['free room', 'empty room', 'vacant room', 'available']): entities['intent'] = 'free_rooms'
        if 'next' in q: entities['relative_time'] = 'next'
        elif any(w in q for w in ['current', 'now', 'right now']): entities['relative_time'] = 'current'
        elif 'tomorrow' in q: entities['relative_time'] = 'tomorrow'
        
        tm = re.search(r'(\d{1,2})[:.]?(\d{2})?\s?(am|pm)', q)
        if tm:
            h = int(tm.group(1))
            m = int(tm.group(2)) if tm.group(2) else 0
            if tm.group(3) == 'pm' and h < 12: h += 12
            if tm.group(3) == 'am' and h == 12: h = 0
            entities['time'] = h * 60 + m

        days_map = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
        for d, idx in days_map.items():
            if d in q: entities['days'].append(idx)
        
        entities['rooms'] = [r.upper() for r in re.findall(r'[a-z]-\d{3}[a-z]?', q)]
        entities['classes'] = [f"{y.upper()} {b.upper()}" for y, b in re.findall(r'\b(fe|se|ty|be|sy)\s+(it|comp|ecs|extc|mech|civil|auto)\b', q)]
        return entities

    def _semantic_filter(self, rows, query, entities, user_name=None):
        if not rows: return []
        now = datetime.now()
        target_day = now.weekday()
        if entities['relative_time'] == 'tomorrow': target_day = (target_day + 1) % 7
        elif entities['days']: target_day = entities['days'][0]

        now_min = entities['time'] if entities['time'] is not None else (now.hour * 60 + now.minute)
        is_personal = entities['personal'] or any(w in query.lower() for w in ['my', 'me', 'i teach'])
        
        filtered = rows if (is_personal and not (entities['days'] or entities['relative_time'])) else [r for r in rows if r['day_of_week'] == target_day]
        if is_personal and user_name:
            u_part = user_name.split()[0].lower()
            filtered = [r for r in filtered if u_part in (r.get('instructor_name') or '').lower()]
        
        if entities['relative_time'] == 'current':
            matches = []
            for r in filtered:
                try:
                    if self._parse_time_min(r['start_time']) <= now_min < self._parse_time_min(r['end_time']): matches.append(r)
                except: continue
            return matches if matches else filtered[:3]
        
        elif entities['relative_time'] == 'next':
            next_c = sorted([r for r in filtered if self._parse_time_min(r['start_time']) >= now_min], key=lambda x: self._parse_time_min(x['start_time']))
            return next_c[:3]

        sw = {'show', 'me', 'the', 'what', 'is', 'when', 'today', 'tomorrow', 'schedule', 'table', 'tell'}
        qw = [w for w in query.lower().split() if w not in sw and len(w) > 1]
        if not qw: return filtered[:5]

        scored = []
        for r in filtered:
            score = 0
            r_str = f"{r.get('class_code','')} {r.get('subject_name','')} {r.get('instructor_name','')} {r.get('room_code','')}".lower()
            if r.get('room_code') in entities['rooms']: score += 20
            if any(c in str(r.get('class_code','')).upper() for c in entities['classes']): score += 15
            for w in qw:
                if w in r_str: score += 5
            if score > 0: scored.append((score, r))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return [x[1] for x in scored[:5]] if scored else filtered[:3]

    def _parse_time_min(self, t_str):
        try:
            t = t_str.upper().strip()
            is_pm, is_am = 'PM' in t, 'AM' in t
            c = re.sub(r'[APM\s]', '', t)
            p = c.split(':')
            h, m = int(p[0]), int(p[1]) if len(p) > 1 else 0
            if is_pm and h < 12: h += 12
            if is_am and h == 12: h = 0
            return h * 60 + m
        except: return 0

    def _generate_ai_response(self, query, results, user_name=None):
        api_key = current_app.config.get('GEMINI_API_KEY')
        if not api_key: return "Database records found but AI service not configured."
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(current_app.config.get('GEMINI_MODEL', 'gemini-2.0-flash'))
            ctx = "\n".join([f"- {r.get('day_name')} {r.get('start_time')}-{r.get('end_time')}: {r.get('subject_name')} in {r.get('room_code')}" for r in results])
            prompt = f"CampusIQ Assistant. Context: {datetime.now().strftime('%A %H:%M')}. User: {user_name or 'Faculty'}.\nQuery: {query}\nData:\n{ctx}\nRule: Max 4 lines, no markdown, be direct."
            resp = model.generate_content(prompt)
            return resp.text.replace('**', '').strip() if resp.text else "Information retrieved but failed to generate summary."
        except Exception as e:
            return f"AI error: {str(e)}"

    def process_query(self, query, college_id=None, user_id=None, user_role=None):
        start = datetime.now()
        entities = self._understand_query(query)
        user_name = self._get_user_name(user_id)
        
        if entities['intent'] == 'free_rooms': results = self._handle_free_rooms(college_id, entities)
        else: results = self._semantic_filter(self._get_timetable_data(college_id), query, entities, user_name)
        
        return {
            'intent': entities['intent'], 
            'response': self._generate_ai_response(query, results, user_name),
            'response_type': 'text',
            'results': results[:5], 
            'suggestions': [],
            'processing_time_ms': int((datetime.now() - start).total_seconds() * 1000)
        }

    def _handle_free_rooms(self, college_id, entities):
        try:
            db = current_app.extensions['sqlalchemy']
            with db.engine.connect() as conn:
                cid_uuid = uuid.UUID(str(college_id))
                all_r = {r._mapping['room_code'] for r in conn.execute(text("SELECT room_code FROM rooms WHERE college_id = :cid AND is_deleted = 0"), {"cid": cid_uuid})}
                now = datetime.now()
                now_min = now.hour * 60 + now.minute
                busy = set()
                res = conn.execute(text("SELECT room_code, start_time, end_time FROM schedules WHERE college_id = :cid AND day_of_week = :day AND is_deleted = 0"), {"cid": cid_uuid, "day": now.weekday()})
                for row in res:
                    m = row._mapping
                    if self._parse_time_min(m['start_time']) <= now_min < self._parse_time_min(m['end_time']): busy.add(m['room_code'])
                free = sorted(list(all_r - busy))
            return [{'room_code': r, 'day_name': 'Today', 'subject_name': 'FREE', 'start_time': 'Now'} for r in free[:10]]
        except: return []

    def get_user_history(self, **kwargs): return []
    def submit_feedback(self, **kwargs): pass
