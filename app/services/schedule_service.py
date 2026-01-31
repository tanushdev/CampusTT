"""
CampusIQ - Schedule Service
Production service for timetable management and CSV bulk imports
"""
import csv
import io
import uuid
from datetime import datetime
from typing import Optional, Dict, List, Any
from flask import current_app, g
from sqlalchemy import text


class ScheduleService:
    """Service for schedule management with multi-tenant isolation"""
    
    def __init__(self, db_path: str = None):
        pass # Not needed for SQLAlchemy
    
    def _get_user_context(self) -> Dict:
        """Get current user context from Flask g"""
        user = getattr(g, 'current_user', None)
        if not user:
            return {'role': None, 'user_id': None, 'college_id': None}
        return user

    def get_schedules(self, college_id: str, day_of_week: Optional[int] = None,
                      class_code: Optional[str] = None, faculty_name: Optional[str] = None,
                      room_code: Optional[str] = None, page: int = 1, per_page: int = 50) -> Dict:
        """Get schedules with filtering and pagination"""
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            query_parts = ["SELECT * FROM schedules WHERE college_id = :cid AND is_deleted = 0"]
            params = {"cid": college_id}
            
            if day_of_week is not None:
                query_parts.append("AND day_of_week = :day")
                params["day"] = day_of_week
            
            if class_code:
                query_parts.append("AND class_code LIKE :class")
                params["class"] = f"%{class_code}%"
                
            if faculty_name:
                query_parts.append("AND instructor_name LIKE :faculty")
                params["faculty"] = f"%{faculty_name}%"
                
            if room_code:
                query_parts.append("AND room_code LIKE :room")
                params["room"] = f"%{room_code}%"
            
            base_query = " ".join(query_parts)
            
            # Count total
            count_query = base_query.replace("SELECT *", "SELECT COUNT(*)")
            total = conn.execute(text(count_query), params).fetchone()[0]
            
            # Pagination
            paged_query = base_query + " ORDER BY day_of_week, start_time LIMIT :limit OFFSET :offset"
            params.update({"limit": per_page, "offset": (page - 1) * per_page})
            
            result = conn.execute(text(paged_query), params)
            items = [dict(row._mapping) for row in result.fetchall()]
            
            return {
                'items': items,
                'total': total,
                'page': page,
                'per_page': per_page,
                'pages': (total + per_page - 1) // per_page if per_page > 0 else 1
            }

    def get_relevant_schedules(self, college_id: str, day: int, time: str, limit: int = 4) -> List[Dict]:
        """Get current and upcoming classes (Ongoing followed by Next)"""
        time = self._normalize_time(time)
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            # First get ongoing classes
            on_res = conn.execute(text("""
                SELECT * FROM schedules 
                WHERE college_id = :cid AND day_of_week = :day AND is_deleted = 0
                AND start_time <= :time AND end_time > :time
                ORDER BY start_time
            """), {"cid": college_id, "day": day, "time": time})
            ongoing = [dict(row._mapping) for row in on_res.fetchall()]
            
            # Then get upcoming classes
            needed = limit - len(ongoing)
            upcoming = []
            if needed > 0:
                up_res = conn.execute(text("""
                    SELECT * FROM schedules 
                    WHERE college_id = :cid AND day_of_week = :day AND is_deleted = 0
                    AND start_time >= :time
                    ORDER BY start_time
                    LIMIT :limit
                """), {"cid": college_id, "day": day, "time": time, "limit": needed})
                upcoming = [dict(row._mapping) for row in up_res.fetchall()]
            
            return ongoing + upcoming

    def get_schedule_by_id(self, schedule_id: str, college_id: str) -> Optional[Dict]:
        """Get a specific schedule entry"""
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            res = conn.execute(text(
                "SELECT * FROM schedules WHERE schedule_id = :sid AND college_id = :cid AND is_deleted = 0"
            ), {"sid": schedule_id, "cid": college_id}).fetchone()
            return dict(res._mapping) if res else None

    def create_schedule(self, college_id: str, data: Dict, created_by: str) -> Dict:
        """Create a single schedule entry"""
        schedule_id = str(uuid.uuid4())
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            try:
                conn.execute(text("""
                    INSERT INTO schedules (
                        schedule_id, college_id, class_code, subject_name, 
                        instructor_name, room_code, day_of_week, 
                        start_time, end_time, created_by, created_at, updated_at
                    ) VALUES (:sid, :cid, :class, :sub, :inst, :room, :day, :start, :end, :cby, :now, :now)
                """), {
                    "sid": schedule_id, "cid": college_id, "class": data.get('class_code'),
                    "sub": data.get('subject_name'), "inst": data.get('instructor_name'),
                    "room": data.get('room_code'), "day": data.get('day_of_week'),
                    "start": data.get('start_time'), "end": data.get('end_time'),
                    "cby": created_by, "now": datetime.utcnow().isoformat()
                })
                conn.commit()
                return {'success': True, 'schedule_id': schedule_id}
            except Exception as e:
                conn.rollback()
                return {'error': 'DATABASE', 'message': str(e)}

    def delete_schedule(self, schedule_id: str, college_id: str, deleted_by: str):
        """Soft delete a schedule entry"""
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            conn.execute(text("""
                UPDATE schedules 
                SET is_deleted = 1, updated_by = :uby, updated_at = :now 
                WHERE schedule_id = :sid AND college_id = :cid
            """), {
                "uby": deleted_by, "now": datetime.utcnow().isoformat(),
                "sid": schedule_id, "cid": college_id
            })
            conn.commit()

    def check_conflicts(self, college_id: str, day_of_week: int, start_time: str, end_time: str,
                        class_code: Optional[str] = None, instructor_name: Optional[str] = None,
                        room_code: Optional[str] = None, exclude_id: Optional[str] = None) -> List[Dict]:
        """Check for scheduling conflicts"""
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            query = """
                SELECT * FROM schedules 
                WHERE college_id = :cid AND day_of_week = :day AND is_deleted = 0
                AND (start_time < :end AND end_time > :start)
            """
            params = {"cid": college_id, "day": day_of_week, "end": end_time, "start": start_time}
            if exclude_id:
                query += " AND schedule_id != :exclude"
                params["exclude"] = exclude_id
            
            result = conn.execute(text(query), params)
            overlaps = [dict(row._mapping) for row in result.fetchall()]
            
            conflicts = []
            for o in overlaps:
                if class_code and o['class_code'] == class_code:
                    conflicts.append({'type': 'CLASS_CONFLICT', 'message': f"Class {class_code} is busy", 'entry': o})
                if instructor_name and o['instructor_name'] == instructor_name:
                    conflicts.append({'type': 'FACULTY_CONFLICT', 'message': f"Instructor {instructor_name} is busy", 'entry': o})
                if room_code and o['room_code'] == room_code:
                    conflicts.append({'type': 'ROOM_CONFLICT', 'message': f"Room {room_code} is busy", 'entry': o})
            return conflicts

    def import_from_csv(self, file_storage, college_id: str, imported_by: str) -> Dict:
        """Bulk import schedules from CSV file"""
        try:
            raw_data = file_storage.stream.read()
            try:
                content = raw_data.decode("utf-8-sig")
            except UnicodeDecodeError:
                content = raw_data.decode("latin-1")
            
            delimiter = ','
            if '\t' in content and content.count('\t') > content.count(','): delimiter = '\t'
            elif ';' in content and content.count(';') > content.count(','): delimiter = ';'
                
            stream = io.StringIO(content, newline=None)
            reader = csv.DictReader(stream, delimiter=delimiter)
        except Exception as e:
            return {'imported': 0, 'skipped': 0, 'errors': [f"File read error: {str(e)}"]}
            
        imported = 0
        skipped = 0
        errors = []
        
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            for row_idx, row in enumerate(reader):
                try:
                    data = {k.lower().strip().replace(' ', '_'): v for k, v in row.items()}
                    day_val = data.get('day') or data.get('weekday') or data.get('day_of_week') or data.get('days')
                    day = self._parse_day(day_val)
                    start = data.get('start_time') or data.get('start') or data.get('from')
                    end = data.get('end_time') or data.get('end') or data.get('to')
                    time_val = data.get('time') or data.get('slot') or data.get('period')
                    
                    if time_val and not (start and end):
                        if '-' in time_val:
                            parts = time_val.split('-')
                            start, end = parts[0].strip(), parts[1].strip()
                        elif ' to ' in time_val.lower():
                            parts = time_val.lower().split(' to ')
                            start, end = parts[0].strip(), parts[1].strip()
                    
                    class_code = data.get('class_code') or data.get('class') or data.get('division') or data.get('batch')
                    subject = data.get('subject_name') or data.get('subject') or data.get('course')
                    faculty = data.get('instructor_name') or data.get('faculty') or data.get('teacher')
                    room = data.get('room_code') or data.get('room') or data.get('location')
                    
                    if day is None or not start or not end or not class_code:
                        skipped += 1
                        errors.append(f"Row {row_idx + 1}: Missing key data")
                        continue
                    
                    conn.execute(text("""
                        INSERT INTO schedules (
                            schedule_id, college_id, class_code, subject_name, 
                            instructor_name, room_code, day_of_week, 
                            start_time, end_time, created_by, created_at, updated_at
                        ) VALUES (:sid, :cid, :class, :sub, :inst, :room, :day, :start, :end, :cby, :now, :now)
                    """), {
                        "sid": str(uuid.uuid4()), "cid": college_id, "class": class_code, "sub": subject,
                        "inst": faculty, "room": room, "day": day,
                        "start": self._normalize_time(start), "end": self._normalize_time(end),
                        "cby": imported_by, "now": datetime.now()
                    })
                    imported += 1
                except Exception as e:
                    errors.append(f"Row {row_idx + 1}: {str(e)}")
                    skipped += 1
            
            conn.commit()
            return {'imported': imported, 'skipped': skipped, 'errors': errors}

    def _normalize_time(self, time_str: str) -> str:
        """Standardize time to 24h HH:MM format"""
        if not time_str: return "00:00"
        t = time_str.upper().strip()
        is_pm = 'PM' in t
        is_am = 'AM' in t
        t = t.replace('AM', '').replace('PM', '').strip()
        try:
            if ':' in t:
                parts = t.split(':')
                h, m = int(parts[0]), int(parts[1][:2])
            else:
                h, m = int(t), 0
            if is_pm and h < 12: h += 12
            if is_am and h == 12: h = 0
            return f"{h:02d}:{m:02d}"
        except: return time_str

    def _parse_day(self, day_str: Optional[str]) -> Optional[int]:
        if not day_str: return None
        d = day_str.lower().strip()
        mapping = {
            'monday': 0, 'mon': 1, '1': 0, 'tuesday': 1, 'tue': 1, '2': 1,
            'wednesday': 2, 'wed': 2, '3': 2, 'thursday': 3, 'thu': 3, '4': 3,
            'friday': 4, 'fri': 4, '5': 4, 'saturday': 5, 'sat': 5, '6': 5,
            'sunday': 6, 'sun': 6, '7': 6, '0': 6
        }
        return mapping.get(d)

    def get_free_rooms(self, college_id: str, day: int, time: str) -> List[str]:
        """Get list of rooms NOT in use at a specific time"""
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            res_all = conn.execute(text("SELECT room_code FROM rooms WHERE college_id = :cid AND is_deleted = 0"), {"cid": college_id})
            all_rooms = [row[0] for row in res_all]
            
            res_busy = conn.execute(text("""
                SELECT DISTINCT room_code FROM schedules 
                WHERE college_id = :cid AND day_of_week = :day AND is_deleted = 0
                AND (start_time <= :time AND end_time > :time)
            """), {"cid": college_id, "day": day, "time": time})
            busy_rooms = [row[0] for row in res_busy]
            return [r for r in all_rooms if r not in busy_rooms]

    def get_free_faculty(self, college_id: str, day: int, time: str) -> List[str]:
        """Get list of faculty NOT in use at a specific time"""
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            res_all = conn.execute(text("SELECT DISTINCT instructor_name FROM schedules WHERE college_id = :cid AND is_deleted = 0"), {"cid": college_id})
            all_faculty = [row[0] for row in res_all if row[0]]
            
            res_busy = conn.execute(text("""
                SELECT DISTINCT instructor_name FROM schedules 
                WHERE college_id = :cid AND day_of_week = :day AND is_deleted = 0
                AND (start_time <= :time AND end_time > :time)
            """), {"cid": college_id, "day": day, "time": time})
            busy_faculty = [row[0] for row in res_busy]
            return [f for f in all_faculty if f not in busy_faculty]

    def get_current_status(self, college_id: str, day: int, time: str) -> Dict:
        """Get combined status of all rooms and faculty for the given time"""
        time = self._normalize_time(time)
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            # All Faculty & Rooms from Schedules (CSV source)
            res_f = conn.execute(text("SELECT DISTINCT instructor_name FROM schedules WHERE college_id = :cid AND is_deleted = 0"), {"cid": college_id})
            all_faculty = [{"name": r[0], "status": "FREE"} for r in res_f if r[0]]
            
            res_r = conn.execute(text("SELECT DISTINCT room_code FROM schedules WHERE college_id = :cid AND is_deleted = 0"), {"cid": college_id})
            all_rooms = [{"code": r[0], "status": "FREE"} for r in res_r if r[0]]

            # Busy state
            bus_r = conn.execute(text("""
                SELECT room_code, class_code, subject_name FROM schedules 
                WHERE college_id = :cid AND day_of_week = :day AND is_deleted = 0
                AND (start_time <= :time AND end_time > :time)
            """), {"cid": college_id, "day": day, "time": time})
            busy_rooms_map = {r[0]: f"{r[1]} - {r[2]}" for r in bus_r}
            
            bus_f = conn.execute(text("""
                SELECT instructor_name, class_code, subject_name FROM schedules 
                WHERE college_id = :cid AND day_of_week = :day AND is_deleted = 0
                AND (start_time <= :time AND end_time > :time)
            """), {"cid": college_id, "day": day, "time": time})
            busy_fac_map = {r[0]: f"{r[1]} - {r[2]}" for r in bus_f}

            for r in all_rooms:
                if r['code'] in busy_rooms_map:
                    r['status'], r['current_class'] = "BUSY", busy_rooms_map[r['code']]
            for f in all_faculty:
                if f['name'] in busy_fac_map:
                    f['status'], f['current_class'] = "BUSY", busy_fac_map[f['name']]

            return {"rooms": all_rooms, "faculty": all_faculty, "timestamp": time, "day_index": day}

    def get_stats(self, college_id: str) -> Dict:
        """Get schedule stats for a college"""
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            res = conn.execute(text("SELECT COUNT(*) FROM schedules WHERE college_id = :cid AND is_deleted = 0"), {"cid": college_id}).fetchone()
            return {'total': res[0]}
