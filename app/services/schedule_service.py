"""
CampusIQ - Schedule Service
Production service for timetable management and CSV bulk imports
"""
import sqlite3
import csv
import io
import uuid
from datetime import datetime
from typing import Optional, Dict, List, Any
from flask import current_app, g


class ScheduleService:
    """Service for schedule management with multi-tenant isolation"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or current_app.config.get('DATABASE_PATH', 'campusiq.db')
    
    def _get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _get_user_context(self) -> Dict:
        """Get current user context from Flask g"""
        user = getattr(g, 'current_user', None)
        if not user:
            return {'role': None, 'user_id': None, 'college_id': None}
        return user

    def get_schedules(self, 
                      college_id: str,
                      day_of_week: Optional[int] = None,
                      class_code: Optional[str] = None,
                      faculty_name: Optional[str] = None,
                      room_code: Optional[str] = None,
                      page: int = 1,
                      per_page: int = 50) -> Dict:
        """Get schedules with filtering and pagination"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            query = "SELECT * FROM schedules WHERE college_id = ? AND is_deleted = 0"
            params = [college_id]
            
            if day_of_week is not None:
                query += " AND day_of_week = ?"
                params.append(day_of_week)
            
            if class_code:
                query += " AND class_code LIKE ?"
                params.append(f"%{class_code}%")
                
            if faculty_name:
                query += " AND instructor_name LIKE ?"
                params.append(f"%{faculty_name}%")
                
            if room_code:
                query += " AND room_code LIKE ?"
                params.append(f"%{room_code}%")
            
            # Count total
            count_query = query.replace("SELECT *", "SELECT COUNT(*)")
            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]
            
            # Pagination
            query += " ORDER BY day_of_week, start_time LIMIT ? OFFSET ?"
            params.extend([per_page, (page - 1) * per_page])
            
            cursor.execute(query, params)
            items = [dict(row) for row in cursor.fetchall()]
            
            return {
                'items': items,
                'total': total,
                'page': page,
                'per_page': per_page,
                'pages': (total + per_page - 1) // per_page if per_page > 0 else 1
            }
        finally:
            conn.close()

    def get_relevant_schedules(self, college_id: str, day: int, time: str, limit: int = 4) -> List[Dict]:
        """Get current and upcoming classes (Ongoing followed by Next)"""
        time = self._normalize_time(time)
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # First get ongoing classes
            cursor.execute("""
                SELECT * FROM schedules 
                WHERE college_id = ? AND day_of_week = ? AND is_deleted = 0
                AND start_time <= ? AND end_time > ?
                ORDER BY start_time
            """, [college_id, day, time, time])
            ongoing = [dict(row) for row in cursor.fetchall()]
            
            # Then get upcoming classes
            needed = limit - len(ongoing)
            upcoming = []
            if needed > 0:
                cursor.execute("""
                    SELECT * FROM schedules 
                    WHERE college_id = ? AND day_of_week = ? AND is_deleted = 0
                    AND start_time >= ?
                    ORDER BY start_time
                    LIMIT ?
                """, [college_id, day, time, needed])
                upcoming = [dict(row) for row in cursor.fetchall()]
            
            return ongoing + upcoming
        finally:
            conn.close()

    def get_schedule_by_id(self, schedule_id: str, college_id: str) -> Optional[Dict]:
        """Get a specific schedule entry"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM schedules WHERE schedule_id = ? AND college_id = ? AND is_deleted = 0",
                [schedule_id, college_id]
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create_schedule(self, college_id: str, data: Dict, created_by: str) -> Dict:
        """Create a single schedule entry"""
        conn = self._get_connection()
        cursor = conn.cursor()
        schedule_id = str(uuid.uuid4())
        
        try:
            cursor.execute("""
                INSERT INTO schedules (
                    schedule_id, college_id, class_code, subject_name, 
                    instructor_name, room_code, day_of_week, 
                    start_time, end_time, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                schedule_id,
                college_id,
                data.get('class_code'),
                data.get('subject_name'),
                data.get('instructor_name'),
                data.get('room_code'),
                data.get('day_of_week'),
                data.get('start_time'),
                data.get('end_time'),
                created_by,
                datetime.utcnow().isoformat(),
                datetime.utcnow().isoformat()
            ])
            conn.commit()
            return {'success': True, 'schedule_id': schedule_id}
        except Exception as e:
            conn.rollback()
            return {'error': 'DATABASE', 'message': str(e)}
        finally:
            conn.close()

    def delete_schedule(self, schedule_id: str, college_id: str, deleted_by: str):
        """Soft delete a schedule entry"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE schedules 
                SET is_deleted = 1, updated_by = ?, updated_at = ? 
                WHERE schedule_id = ? AND college_id = ?
            """, [deleted_by, datetime.utcnow().isoformat(), schedule_id, college_id])
            conn.commit()
        finally:
            conn.close()

    def check_conflicts(self, 
                        college_id: str, 
                        day_of_week: int, 
                        start_time: str, 
                        end_time: str,
                        class_code: Optional[str] = None,
                        instructor_name: Optional[str] = None,
                        room_code: Optional[str] = None,
                        exclude_id: Optional[str] = None) -> List[Dict]:
        """Check for scheduling conflicts"""
        conn = self._get_connection()
        cursor = conn.cursor()
        conflicts = []
        
        try:
            # Base query: overlap check
            # (start1 < end2) AND (end1 > start2)
            query = """
                SELECT * FROM schedules 
                WHERE college_id = ? AND day_of_week = ? AND is_deleted = 0
                AND (start_time < ? AND end_time > ?)
            """
            params = [college_id, day_of_week, end_time, start_time]
            
            if exclude_id:
                query += " AND schedule_id != ?"
                params.append(exclude_id)
            
            cursor.execute(query, params)
            overlaps = [dict(row) for row in cursor.fetchall()]
            
            for o in overlaps:
                if class_code and o['class_code'] == class_code:
                    conflicts.append({'type': 'CLASS_CONFLICT', 'message': f"Class {class_code} is busy", 'entry': o})
                if instructor_name and o['instructor_name'] == instructor_name:
                    conflicts.append({'type': 'FACULTY_CONFLICT', 'message': f"Instructor {instructor_name} is busy", 'entry': o})
                if room_code and o['room_code'] == room_code:
                    conflicts.append({'type': 'ROOM_CONFLICT', 'message': f"Room {room_code} is busy", 'entry': o})
            
            return conflicts
        finally:
            conn.close()

    def import_from_csv(self, file_storage, college_id: str, imported_by: str) -> Dict:
        """Bulk import schedules from CSV file"""
        try:
            raw_data = file_storage.stream.read()
            try:
                content = raw_data.decode("utf-8-sig") # Handles UTF-8 with BOM
            except UnicodeDecodeError:
                content = raw_data.decode("latin-1") # Common Excel fallback
                
            # Auto-detect delimiter
            delimiter = ','
            if '\t' in content and content.count('\t') > content.count(','):
                delimiter = '\t'
            elif ';' in content and content.count(';') > content.count(','):
                delimiter = ';'
                
            stream = io.StringIO(content, newline=None)
            reader = csv.DictReader(stream, delimiter=delimiter)
        except Exception as e:
            return {'imported': 0, 'skipped': 0, 'errors': [f"File read error: {str(e)}"]}
            
        imported = 0
        skipped = 0
        errors = []
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            for row_idx, row in enumerate(reader):
                try:
                    # Clean keys (case-insensitive and strip)
                    data = {k.lower().strip().replace(' ', '_'): v for k, v in row.items()}
                    
                    # Mapping common CSV headers
                    day_val = data.get('day') or data.get('weekday') or data.get('day_of_week') or data.get('days')
                    day = self._parse_day(day_val)
                    
                    time_val = data.get('time') or data.get('slot') or data.get('period')
                    start = data.get('start_time') or data.get('start') or data.get('from')
                    end = data.get('end_time') or data.get('end') or data.get('to')
                    
                    # Split time range if found (e.g. "9:00 - 10:00")
                    if time_val and not (start and end):
                        if '-' in time_val:
                            parts = time_val.split('-')
                            start = parts[0].strip()
                            end = parts[1].strip()
                        elif ' to ' in time_val.lower():
                            parts = time_val.lower().split(' to ')
                            start = parts[0].strip()
                            end = parts[1].strip()
                    
                    class_code = data.get('class_code') or data.get('class') or data.get('division') or data.get('batch') or data.get('group')
                    subject = data.get('subject_name') or data.get('subject') or data.get('subject_code') or data.get('course')
                    faculty = data.get('instructor_name') or data.get('faculty') or data.get('teacher') or data.get('instructor')
                    room = data.get('room_code') or data.get('room') or data.get('location') or data.get('venue')
                    
                    if day is None or not start or not end or not class_code:
                        skipped += 1
                        errors.append(f"Row {row_idx + 1}: Missing Day({day_val}), Time({start}-{end}), or Class({class_code})")
                        continue
                    
                    # Create entry
                    cursor.execute("""
                        INSERT INTO schedules (
                            schedule_id, college_id, class_code, subject_name, 
                            instructor_name, room_code, day_of_week, 
                            start_time, end_time, created_by, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, [
                        str(uuid.uuid4()),
                        college_id,
                        class_code,
                        subject,
                        faculty,
                        room,
                        day,
                        self._normalize_time(start),
                        self._normalize_time(end),
                        imported_by,
                        datetime.now(),
                        datetime.now()
                    ])
                    imported += 1
                    
                except Exception as e:
                    errors.append(f"Row {row_idx + 1}: {str(e)}")
                    skipped += 1
            
            conn.commit()
            return {'imported': imported, 'skipped': skipped, 'errors': errors}
        except Exception as e:
            conn.rollback()
            return {'imported': 0, 'skipped': skipped, 'errors': [str(e)]}
        finally:
            conn.close()

    def _normalize_time(self, time_str: str) -> str:
        """Standardize time to 24h HH:MM format for string comparison"""
        if not time_str: return "00:00"
        t = time_str.upper().strip()
        
        # Handle AM/PM
        is_pm = 'PM' in t
        is_am = 'AM' in t
        t = t.replace('AM', '').replace('PM', '').strip()
        
        try:
            if ':' in t:
                parts = t.split(':')
                h = int(parts[0])
                m = int(parts[1][:2]) # Handle "10:00PM" -> "10", "00"
            else:
                # Handle "9" -> "9:00"
                h = int(t)
                m = 0
                
            if is_pm and h < 12: h += 12
            if is_am and h == 12: h = 0
            
            return f"{h:02d}:{m:02d}"
        except:
            return time_str # Fallback

    def _parse_day(self, day_str: Optional[str]) -> Optional[int]:
        """Convert string day to index (0=Monday)"""
        if not day_str: return None
        d = day_str.lower().strip()
        
        # Handle "Day 1", "Day 2" format
        if 'day' in d:
            try:
                # Remove non-numeric characters to get "1" from "Day 1" or "Day1"
                import re
                nums = re.findall(r'\d+', d)
                if nums:
                    val = int(nums[0])
                    return (val - 1) % 7
            except:
                pass

        # Custom mapping: 1=Mon, 2=Tue, ..., 7=Sun
        mapping = {
            'monday': 0, 'mon': 0, '1': 0,
            'tuesday': 1, 'tue': 1, '2': 1,
            'wednesday': 2, 'wed': 2, '3': 2,
            'thursday': 3, 'thu': 3, '4': 3,
            'friday': 4, 'fri': 4, '5': 4,
            'saturday': 5, 'sat': 5, '6': 5,
            'sunday': 6, 'sun': 6, '7': 6,
            '0': 6 # 0 as Sunday fallback
        }
        return mapping.get(d)

    def get_free_rooms(self, college_id: str, day: int, time: str) -> List[str]:
        """Get list of rooms NOT in use at a specific time"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # Get all rooms for college
            cursor.execute("SELECT room_code FROM rooms WHERE college_id = ? AND is_deleted = 0", [college_id])
            all_rooms = [r['room_code'] for r in cursor.fetchall()]
            
            # Get busy rooms
            cursor.execute("""
                SELECT DISTINCT room_code FROM schedules 
                WHERE college_id = ? AND day_of_week = ? AND is_deleted = 0
                AND (start_time <= ? AND end_time > ?)
            """, [college_id, day, time, time])
            busy_rooms = [r['room_code'] for r in cursor.fetchall()]
            
            return [r for r in all_rooms if r not in busy_rooms]
        finally:
            conn.close()

    def get_free_faculty(self, college_id: str, day: int, time: str) -> List[str]:
        """Get list of faculty NOT in use at a specific time"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # For simplicity, we get faculty names from the schedules table or faculty table
            cursor.execute("SELECT DISTINCT instructor_name FROM schedules WHERE college_id = ? AND is_deleted = 0", [college_id])
            all_faculty = [r['instructor_name'] for r in cursor.fetchall() if r['instructor_name']]
            
            cursor.execute("""
                SELECT DISTINCT instructor_name FROM schedules 
                WHERE college_id = ? AND day_of_week = ? AND is_deleted = 0
                AND (start_time <= ? AND end_time > ?)
            """, [college_id, day, time, time])
            busy_faculty = [r['instructor_name'] for r in cursor.fetchall()]
            
            return [f for f in all_faculty if f not in busy_faculty]
        finally:
            conn.close()

    def get_current_status(self, college_id: str, day: int, time: str) -> Dict:
        """Get combined status of all rooms and faculty for the given time"""
        time = self._normalize_time(time)
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # All Faculty from Timetable (CSV)
            cursor.execute("SELECT DISTINCT instructor_name FROM schedules WHERE college_id = ? AND is_deleted = 0", [college_id])
            all_faculty = [{"name": r['instructor_name'], "status": "FREE"} for r in cursor.fetchall() if r['instructor_name']]
            
            # All Rooms from Timetable (CSV)
            cursor.execute("SELECT DISTINCT room_code FROM schedules WHERE college_id = ? AND is_deleted = 0", [college_id])
            all_rooms = [{"code": r['room_code'], "status": "FREE"} for r in cursor.fetchall() if r['room_code']]

            # Busy Rooms
            cursor.execute("""
                SELECT DISTINCT room_code, class_code, subject_name FROM schedules 
                WHERE college_id = ? AND day_of_week = ? AND is_deleted = 0
                AND (start_time <= ? AND end_time > ?)
            """, [college_id, day, time, time])
            busy_rooms_data = {r['room_code']: f"{r['class_code']} - {r['subject_name']}" for r in cursor.fetchall()}
            
            # Busy Faculty
            cursor.execute("""
                SELECT DISTINCT instructor_name, class_code, subject_name FROM schedules 
                WHERE college_id = ? AND day_of_week = ? AND is_deleted = 0
                AND (start_time <= ? AND end_time > ?)
            """, [college_id, day, time, time])
            busy_faculty_data = {r['instructor_name']: f"{r['class_code']} - {r['subject_name']}" for r in cursor.fetchall()}

            # Update statuses
            for r in all_rooms:
                if r['code'] in busy_rooms_data:
                    r['status'] = "BUSY"
                    r['current_class'] = busy_rooms_data[r['code']]

            for f in all_faculty:
                if f['name'] in busy_faculty_data:
                    f['status'] = "BUSY"
                    f['current_class'] = busy_faculty_data[f['name']]

            return {
                "rooms": all_rooms,
                "faculty": all_faculty,
                "timestamp": time,
                "day_index": day
            }
        finally:
            conn.close()

    def get_stats(self, college_id: str) -> Dict:
        """Get schedule stats for a college"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM schedules WHERE college_id = ? AND is_deleted = 0", [college_id])
            return {'total': cursor.fetchone()[0]}
        finally:
            conn.close()
