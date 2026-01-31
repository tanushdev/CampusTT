"""
CampusIQ - Schedule Service
Production service for timetable management and CSV bulk imports
"""
import csv
import io
import re
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
            cid_uuid = uuid.UUID(str(college_id))
            query_parts = ["FROM schedules WHERE college_id = :cid AND is_deleted = 0"]
            params = {"cid": cid_uuid}
            
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
            
            base_q = " ".join(query_parts)
            total = conn.execute(text(f"SELECT COUNT(*) {base_q}"), params).fetchone()[0]
            
            params.update({"limit": per_page, "offset": (page - 1) * per_page})
            res = conn.execute(text(f"SELECT * {base_q} ORDER BY day_of_week, start_time LIMIT :limit OFFSET :offset"), params)
            
            return {
                'items': [dict(row._mapping) for row in res], 'total': total,
                'page': page, 'per_page': per_page, 'pages': (total + per_page - 1) // per_page if per_page > 0 else 1
            }

    def get_relevant_schedules(self, college_id: str, day: int, time: str, limit: int = 4) -> List[Dict]:
        """Get current and upcoming classes"""
        time = self._normalize_time(time)
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            cid_uuid = uuid.UUID(str(college_id))
            on_res = conn.execute(text("""
                SELECT * FROM schedules 
                WHERE college_id = :cid AND day_of_week = :day AND is_deleted = 0
                AND start_time <= :time AND end_time > :time ORDER BY start_time
            """), {"cid": cid_uuid, "day": day, "time": time})
            ongoing = [dict(row._mapping) for row in on_res]
            
            needed = limit - len(ongoing)
            upcoming = []
            if needed > 0:
                up_res = conn.execute(text("""
                    SELECT * FROM schedules 
                    WHERE college_id = :cid AND day_of_week = :day AND is_deleted = 0
                    AND start_time >= :time ORDER BY start_time LIMIT :limit
                """), {"cid": cid_uuid, "day": day, "time": time, "limit": needed})
                upcoming = [dict(row._mapping) for row in up_res]
            
            return ongoing + upcoming

    def get_schedule_by_id(self, schedule_id: str, college_id: str) -> Optional[Dict]:
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            res = conn.execute(text("SELECT * FROM schedules WHERE schedule_id = :sid AND college_id = :cid AND is_deleted = 0"),
                               {"sid": uuid.UUID(str(schedule_id)), "cid": uuid.UUID(str(college_id))}).fetchone()
            return dict(res._mapping) if res else None

    def create_schedule(self, college_id: str, data: Dict, created_by: str) -> Dict:
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            try:
                sid = uuid.uuid4()
                now = datetime.utcnow()
                conn.execute(text("""
                    INSERT INTO schedules (
                        schedule_id, college_id, class_code, subject_name, instructor_name, room_code, 
                        day_of_week, start_time, end_time, created_by, created_at, updated_at
                    ) VALUES (:sid, :cid, :class, :sub, :inst, :room, :day, :start, :end, :cby, :now, :now)
                """), {
                    "sid": sid, "cid": uuid.UUID(str(college_id)), "class": data.get('class_code'),
                    "sub": data.get('subject_name'), "inst": data.get('instructor_name'),
                    "room": data.get('room_code'), "day": data.get('day_of_week'),
                    "start": data.get('start_time'), "end": data.get('end_time'),
                    "cby": uuid.UUID(str(created_by)), "now": now
                })
                conn.commit()
                return {'success': True, 'schedule_id': str(sid)}
            except Exception as e:
                conn.rollback()
                return {'error': 'DATABASE', 'message': str(e)}

    def delete_schedule(self, schedule_id: str, college_id: str, deleted_by: str):
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            conn.execute(text("UPDATE schedules SET is_deleted = 1, updated_by = :uby, updated_at = :now WHERE schedule_id = :sid AND college_id = :cid"),
                         {"uby": uuid.UUID(str(deleted_by)), "now": datetime.utcnow(), "sid": uuid.UUID(str(schedule_id)), "cid": uuid.UUID(str(college_id))})
            conn.commit()

    def delete_all_schedules(self, college_id: str, deleted_by: str):
        """Bulk delete all schedules for a college"""
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            conn.execute(text("""
                UPDATE schedules 
                SET is_deleted = 1, updated_by = :uby, updated_at = :now 
                WHERE college_id = :cid AND is_deleted = 0
            """), {
                "uby": uuid.UUID(str(deleted_by)), 
                "now": datetime.utcnow(), 
                "cid": uuid.UUID(str(college_id))
            })
            conn.commit()

    def check_conflicts(self, college_id: str, day_of_week: int, start_time: str, end_time: str,
                        class_code: Optional[str] = None, instructor_name: Optional[str] = None,
                        room_code: Optional[str] = None, exclude_id: Optional[str] = None) -> List[Dict]:
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            cid_uuid = uuid.UUID(str(college_id))
            query = "SELECT * FROM schedules WHERE college_id = :cid AND day_of_week = :day AND is_deleted = 0 AND (start_time < :end AND end_time > :start)"
            params = {"cid": cid_uuid, "day": day_of_week, "end": end_time, "start": start_time}
            if exclude_id:
                query += " AND schedule_id != :exclude"
                params["exclude"] = uuid.UUID(str(exclude_id))
            
            res = conn.execute(text(query), params)
            overlaps = [dict(row._mapping) for row in res]
            
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
            # Use .read() which is safer than .stream.read()
            raw_data = file_storage.read()
            if not raw_data:
                return {'imported': 0, 'skipped': 0, 'errors': ["File is empty"]}
                
            try: content = raw_data.decode("utf-8-sig")
            except UnicodeDecodeError: 
                try: content = raw_data.decode("utf-8")
                except UnicodeDecodeError: content = raw_data.decode("latin-1")
            
            stream = io.StringIO(content, newline=None)
            # Try to detect delimiter and handle TSV
            sample = content[:4096]
            dialect = 'excel'
            if sample:
                try:
                    # Check for tab separation which is common in some exports
                    if '\t' in sample and sample.count('\t') > sample.count(','):
                        dialect = 'excel-tab'
                    else:
                        sniffer = csv.Sniffer()
                        dialect = sniffer.sniff(sample)
                except: dialect = 'excel'
            
            reader = csv.DictReader(stream, dialect=dialect)
        except Exception as e: 
            current_app.logger.error(f"CSV Parse Error: {e}")
            return {'imported': 0, 'skipped': 0, 'errors': [f"File read error: {str(e)}"]}
            
        imported, skipped, errors = 0, 0, []
        db = current_app.extensions['sqlalchemy']
        
        with db.engine.connect() as conn:
            # phase 1: Ensure table and init progress
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS import_progress (
                    college_id UUID PRIMARY KEY,
                    total_rows INTEGER DEFAULT 0,
                    processed_rows INTEGER DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'idle',
                    message TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("""
                INSERT INTO import_progress (college_id, total_rows, processed_rows, status, message, updated_at)
                VALUES (:cid, 0, 0, 'processing', 'Reading file...', NOW())
                ON CONFLICT (college_id) DO UPDATE SET 
                total_rows = 0, processed_rows = 0, status = 'processing', message = 'Reading file...', updated_at = NOW()
            """), {"cid": uuid.UUID(str(college_id))})
            conn.commit()

            try:
                cid_uuid = uuid.UUID(str(college_id))
                uby_uuid = uuid.UUID(str(imported_by))
                now = datetime.utcnow()
                
                # phase 2: Load rows
                first_row = next(reader, None)
                if first_row:
                    # Log detected columns for debugging
                    keys = [str(k).lower().strip().replace(' ', '_') for k in first_row.keys() if k]
                    current_app.logger.info(f"CSV Headers detected: {keys}")
                    rows = [first_row] + list(reader)
                else:
                    return {'imported': 0, 'skipped': 0, 'errors': ["CSV has no data rows"]}

                current_app.logger.info(f"Starting import of {len(rows)} rows for college {college_id}")

                # Update total
                conn.execute(text("UPDATE import_progress SET total_rows = :total, message = 'Processing data...' WHERE college_id = :cid"), 
                                {"cid": cid_uuid, "total": len(rows)})
                conn.commit()
                
                all_params = []
                for row_idx, row in enumerate(rows):
                    try:
                        # Safely handle None keys or non-string keys
                        data = {}
                        for k, v in row.items():
                            if k:
                                clean_k = str(k).lower().strip().replace(' ', '_').replace('(', '').replace(')', '')
                                data[clean_k] = v
                        
                        day_val = data.get('day') or data.get('day_of_week') or data.get('weekday') or data.get('date')
                        day = self._parse_day(day_val)
                        
                        time_val = data.get('time') or data.get('timeslot') or data.get('slot')
                        if time_val and '-' in str(time_val):
                            t_parts = str(time_val).split('-')
                            start_val = t_parts[0].strip()
                            end_val = t_parts[1].strip()
                        else:
                            start_val = data.get('start_time') or data.get('start') or data.get('from') or data.get('start_at')
                            end_val = data.get('end_time') or data.get('end') or data.get('to') or data.get('end_at')
                            
                        # Handle cases where From/To are like "9:00" without AM/PM but To is "5:00 PM"
                        start = self._normalize_time(start_val)
                        end = self._normalize_time(end_val)
                        
                        class_code = data.get('class_code') or data.get('class') or data.get('group') or data.get('batch') or data.get('division') or data.get('year')
                        subject = data.get('subject_name') or data.get('subject') or data.get('course') or data.get('module')
                        faculty = data.get('instructor_name') or data.get('instructor') or data.get('faculty') or data.get('teacher') or data.get('prof')
                        room = data.get('room_code') or data.get('room') or data.get('location') or data.get('room_no') or data.get('venue')
                        
                        # Strip quotes from room names like "J-104A1"
                        if room: room = str(room).strip('"\' ')
                        
                        if day is None or not start or not end or not class_code:
                            missing = []
                            if day is None: missing.append(f"day(val:{day_val})")
                            if not start or start == "00:00": missing.append("start")
                            if not end or end == "00:00": missing.append("end")
                            if not class_code: missing.append("group/class")
                            errors.append(f"Row {row_idx + 1}: Missing {', '.join(missing)}")
                            skipped += 1; continue
                        
                        all_params.append({
                            "sid": uuid.uuid4(), "cid": cid_uuid, "class": str(class_code), "sub": str(subject or ''),
                            "inst": str(faculty or ''), "room": str(room or ''), "day": int(day), "start": str(start), "end": str(end),
                            "cby": uby_uuid, "now": now
                        })
                    except Exception as e:
                        errors.append(f"Row {row_idx + 1}: {str(e)}")
                        skipped += 1
                
                # phase 3: Batch Insert
                chunk_size = 500
                for i in range(0, len(all_params), chunk_size):
                    chunk = all_params[i:i + chunk_size]
                    batch_trans = conn.begin()
                    try:
                        conn.execute(text("""
                            INSERT INTO schedules (
                                schedule_id, college_id, class_code, subject_name, instructor_name, room_code, 
                                day_of_week, start_time, end_time, created_by, created_at, updated_at
                            ) VALUES (:sid, :cid, :class, :sub, :inst, :room, :day, :start, :end, :cby, :now, :now)
                        """), chunk)
                        batch_trans.commit()
                        imported += len(chunk)
                        
                        # Update progress using same connection
                        conn.execute(text("UPDATE import_progress SET processed_rows = :proc, message = :msg WHERE college_id = :cid"), 
                                        {"cid": cid_uuid, "proc": imported, "msg": f"Saving {imported}/{len(all_params)}..."})
                        conn.commit()
                        current_app.logger.info(f"Progress: {imported}/{len(all_params)} rows imported...")
                    except Exception as e:
                        batch_trans.rollback()
                        errors.append(f"Batch {i//chunk_size + 1} failure: {str(e)}")

                # phase 4: Cleanup
                conn.execute(text("UPDATE import_progress SET status = 'idle', message = 'Complete!', processed_rows = total_rows WHERE college_id = :cid"), {"cid": cid_uuid})
                conn.commit()

                return {'imported': imported, 'skipped': skipped, 'errors': errors}
            except Exception as e:
                current_app.logger.error(f"Import process failed for college {college_id}: {e}")
                # Ensure progress status is updated even on failure
                try:
                    conn.execute(text("UPDATE import_progress SET status = 'failed', message = :msg WHERE college_id = :cid"), 
                                 {"cid": cid_uuid, "msg": f"Import failed: {str(e)}"})
                    conn.commit()
                except Exception as update_e:
                    current_app.logger.error(f"Failed to update import progress status after error: {update_e}")
                return {'error': 'DATABASE', 'message': str(e)}

    def get_import_progress(self, college_id: str) -> Dict:
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            res = conn.execute(text("SELECT total_rows, processed_rows, status, message FROM import_progress WHERE college_id = :cid"), 
                             {"cid": uuid.UUID(str(college_id))}).fetchone()
            if not res:
                return {'status': 'idle', 'total': 0, 'processed': 0}
            return {
                'total': res[0],
                'processed': res[1],
                'status': res[2],
                'message': res[3]
            }

    def _normalize_time(self, time_str: str) -> str:
        if not time_str: return "00:00"
        t = time_str.upper().strip()
        is_pm, is_am = 'PM' in t, 'AM' in t
        t = t.replace('AM', '').replace('PM', '').strip()
        try:
            if ':' in t:
                parts = t.split(':')
                h, m = int(parts[0]), int(parts[1][:2])
            else: h, m = int(t), 0
            if is_pm and h < 12: h += 12
            if is_am and h == 12: h = 0
            return f"{h:02d}:{m:02d}"
        except: return time_str

    def _parse_day(self, day_str: Optional[str]) -> Optional[int]:
        if not day_str: return None
        d = str(day_str).lower().strip()
        
        # Handle "Day 1", "Day 2" formats
        day_match = re.search(r'day\s*(\d+)', d)
        if day_match:
            try:
                # Map Day 1 -> Mon (0), Day 2 -> Tue (1), etc.
                return (int(day_match.group(1)) - 1) % 7
            except: pass

        mapping = {'monday': 0, 'mon': 0, 'tuesday': 1, 'tue': 1, 'wednesday': 2, 'wed': 2, 'thursday': 3, 'thu': 3, 'friday': 4, 'fri': 4, 'saturday': 5, 'sat': 5, 'sunday': 6, 'sun': 6}
        try: return mapping.get(d) if d in mapping else int(d) % 7
        except: return None

    def get_free_rooms(self, college_id: str, day: int, time: str) -> List[str]:
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            cid_uuid = uuid.UUID(str(college_id))
            res_all = conn.execute(text("SELECT room_code FROM rooms WHERE college_id = :cid AND is_deleted = 0"), {"cid": cid_uuid})
            all_rooms = [row[0] for row in res_all]
            res_busy = conn.execute(text("SELECT DISTINCT room_code FROM schedules WHERE college_id = :cid AND day_of_week = :day AND is_deleted = 0 AND (start_time <= :time AND end_time > :time)"), {"cid": cid_uuid, "day": day, "time": time})
            busy_rooms = [row[0] for row in res_busy]
            return [r for r in all_rooms if r not in busy_rooms]

    def get_current_status(self, college_id: str, day: int, time: str) -> Dict:
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            cid_uuid = uuid.UUID(str(college_id))
            res_f = conn.execute(text("SELECT DISTINCT instructor_name FROM schedules WHERE college_id = :cid AND is_deleted = 0"), {"cid": cid_uuid})
            all_faculty = [{"name": r[0], "status": "FREE"} for r in res_f if r[0]]
            res_r = conn.execute(text("SELECT DISTINCT room_code FROM schedules WHERE college_id = :cid AND is_deleted = 0"), {"cid": cid_uuid})
            all_rooms = [{"code": r[0], "status": "FREE"} for r in res_r if r[0]]
            
            busy_q = "AND day_of_week = :day AND is_deleted = 0 AND (start_time <= :time AND end_time > :time)"
            bus_r = conn.execute(text(f"SELECT room_code, class_code, subject_name FROM schedules WHERE college_id = :cid {busy_q}"), {"cid": cid_uuid, "day": day, "time": time})
            busy_rooms_map = {r[0]: f"{r[1]} - {r[2]}" for r in bus_r}
            bus_f = conn.execute(text(f"SELECT instructor_name, class_code, subject_name FROM schedules WHERE college_id = :cid {busy_q}"), {"cid": cid_uuid, "day": day, "time": time})
            busy_fac_map = {r[0]: f"{r[1]} - {r[2]}" for r in bus_f}

            for r in all_rooms:
                if r['code'] in busy_rooms_map: r['status'], r['current_class'] = "BUSY", busy_rooms_map[r['code']]
            for f in all_faculty:
                if f['name'] in busy_fac_map: f['status'], f['current_class'] = "BUSY", busy_fac_map[f['name']]
            return {"rooms": all_rooms, "faculty": all_faculty, "timestamp": time, "day_index": day}

    def get_stats(self, college_id: str) -> Dict:
        db = current_app.extensions['sqlalchemy']
        with db.engine.connect() as conn:
            res = conn.execute(text("SELECT COUNT(*) FROM schedules WHERE college_id = :cid AND is_deleted = 0"), {"cid": uuid.UUID(str(college_id))}).fetchone()
            return {'total': int(res[0])}
