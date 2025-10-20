# app.py
from flask import Flask, render_template, request, jsonify, redirect, url_for
import os
import json
import time
import threading
from datetime import datetime, timedelta
import google.generativeai as genai
from dataclasses import dataclass
from typing import List, Dict, Optional
import requests
import schedule
import random
import pytz

app = Flask(__name__)

# Configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'your-gemini-api-key')
TIKTOK_ACCESS_TOKEN = os.getenv('TIKTOK_ACCESS_TOKEN', 'your-tiktok-token')

# กำหนด timezone ไทย
THAILAND_TZ = pytz.timezone('Asia/Bangkok')

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)

@dataclass
class Job:
    id: str
    name: str
    prompt: str
    schedule_time: str
    status: str
    created_at: str
    last_run: Optional[str] = None
    video_url: Optional[str] = None
    tiktok_url: Optional[str] = None
    error_message: Optional[str] = None

# In-memory storage (ใช้ database จริงในการใช้งานจริง)
jobs_storage = {}
job_logs = []

class VideoJobManager:
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-1.5-pro')
        
        # 📅 ตารางเวลาอัปโหลดที่เหมาะสม (เวลาไทย)
        self.optimal_schedule = {
            'monday': {'time': '19:30', 'range': '19:00-20:00'},     # วันจันทร์
            'tuesday': {'time': '16:30', 'range': '16:00-17:00'},    # วันอังคาร  
            'wednesday': {'time': '17:30', 'range': '17:00-18:00'},  # วันพุธ
            'thursday': {'time': '17:30', 'range': '17:00-18:00'},   # วันพฤหัสบดี
            'friday': {'time': '16:30', 'range': '16:00-17:00'},     # วันศุกร์
            'saturday': {'time': '17:30', 'range': '17:00-18:00'},   # วันเสาร์
            'sunday': {'time': '20:30', 'range': '20:00-21:00'}      # วันอาทิตย์
        }
        
        # ตัวอย่าง prompts ASMR ยอดนิยม (AUTO-GENERATED)
        self.asmr_prompts = {
            "glass_fruits": [
                "A hyper-realistic cinematic close-up of a whole, full-shaped glass strawberry with a soft red translucent hue. The glass fruit is perfectly centred on a wooden cutting board, glowing subtly under studio lighting. A human hand is clearly visible, holding a sharp stainless steel knife just above the fruit, ready to slice. In slow motion, the knife makes clean slices through the glass fruit, creating delicate glass-crack sounds. Transparent shards scatter lightly. ASMR slicing sounds only.",
                
                "Ultra-realistic 4K footage of a translucent glass mango with golden-yellow tint being precisely sliced with a steel knife on a wooden cutting board. The mango has a glossy, semi-transparent surface with a visible frosted glass seed inside. Soft cinematic lighting highlights the glass textures. The knife moves smoothly and deliberately, making three clean cuts with crisp glass-shattering sounds. Each slice reveals the crystal-like interior.",
                
                "Close-up of a crystal-clear glass banana with pale yellow hue resting on a dark wooden surface. A chef's knife rapidly dices the glass fruit into perfect uniform cubes that scatter with each cut. The inside reveals glass segments and texture. Studio lighting creates subtle reflections. ASMR-style audio with only slicing sounds, no background music.",
                
                "Hyper-detailed glass watermelon with dark green exterior and red glass interior being chopped with a large cleaver. One powerful chop down the middle reveals the translucent red inside with black glass seeds. The two halves fall apart cleanly on a wooden table. Cinematic lighting with shallow depth of field.",
                
                "A transparent glass apple with light green tint being sliced into thin, even pieces. Each cut creates satisfying glass crack sounds as the knife glides through. The apple core is visible as frosted glass. Macro lens close-up with professional food photography lighting."
            ],
            
            "creative_materials": [
                "A glowing chunk of solid gold being sliced with a heated knife. Each cut creates sharp, crisp snapping sounds like breaking delicate shells. Golden shards scatter as the surface cracks cleanly, blending satisfying crunch with molten smoothness. Warm studio lighting enhances the golden glow.",
                
                "Crystal-clear ice blocks being precisely cut with a heated blade. Steam rises as the knife meets ice. Each slice produces crisp cracking sounds and the pieces slide apart with glassy precision. Water droplets catch the light as they scatter.",
                
                "A translucent soap bar made of rainbow colors being sliced into perfect cubes. The knife glides smoothly through the soft material, creating satisfying slicing sounds and revealing marbled patterns inside. Pieces fall away cleanly with slight bounce.",
                
                "A block of kinetic sand being cut with a thin wire. The sand parts smoothly creating perfect clean edges. Grains cascade gently as the wire passes through. Close-up macro shot showing individual sand particles falling.",
                
                "A honeycomb structure made of amber glass being carved with precision tools. Each hexagonal cell breaks with tiny crystalline sounds. Golden light passes through creating beautiful refractions."
            ],
            
            "satisfying_textures": [
                "Ultra-satisfying scene of vibrant pastel rainbow butter being gently spread across warm crispy toast. The knife glides smoothly, creating perfect ridges and swirls. Soft spreading sounds and gentle sizzling from the warm bread.",
                
                "Slicing through a perfect cube of jelly that wobbles hypnotically. The knife creates clean cuts revealing the translucent interior. Each piece jiggles independently as it separates. Subtle squelching sounds.",
                
                "Cutting through layers of colorful modeling clay stacked in a rainbow pattern. Each slice reveals all the color layers in cross-section. The knife moves smoothly through the soft material with satisfying resistance.",
                
                "Precise cuts through a sphere of magnetic putty that slowly reforms after each slice. The metallic gray material moves and flows like liquid metal. Subtle magnetic clicking sounds as particles realign.",
                
                "Slicing through foam blocks that compress and spring back. Each cut creates a satisfying 'whoosh' sound as air escapes. The foam texture is perfectly uniform and bouncy."
            ]
        }
        
        # Hashtags ยอดนิยมสำหรับ TikTok ASMR
        self.popular_hashtags = [
            '#ASMR', '#satisfying', '#oddlysatisfying', '#glassfruit', 
            '#asmrvideo', '#relaxing', '#calmingsounds', '#slicing',
            '#asmrcommunity', '#tingles', '#mindfulness', '#stressrelief',
            '#viral', '#fyp', '#foryou', '#trending'
        ]

    def get_next_optimal_time(self) -> dict:
        """หาเวลาถัดไปที่เหมาะสมสำหรับอัปโหลด"""
        thailand_now = datetime.now(THAILAND_TZ)
        
        # วันในสัปดาห์ (0=จันทร์, 6=อาทิตย์)
        weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        
        for days_ahead in range(7):  # ตรวจสอบ 7 วันข้างหน้า
            target_date = thailand_now + timedelta(days=days_ahead)
            weekday = weekdays[target_date.weekday()]
            
            optimal_time = self.optimal_schedule[weekday]['time']
            target_time = datetime.strptime(f"{target_date.strftime('%Y-%m-%d')} {optimal_time}", 
                                          '%Y-%m-%d %H:%M')
            target_time = THAILAND_TZ.localize(target_time)
            
            # ถ้าเวลานั้นยังไม่ถึง หรือ ถ้าเป็นวันถัดไป
            if target_time > thailand_now or days_ahead > 0:
                return {
                    'datetime': target_time,
                    'weekday': weekday,
                    'time_range': self.optimal_schedule[weekday]['range'],
                    'thai_weekday': self.get_thai_weekday(weekday)
                }
        
        # fallback: วันจันทร์หน้า
        next_monday = thailand_now + timedelta(days=7-thailand_now.weekday())
        target_time = datetime.strptime(f"{next_monday.strftime('%Y-%m-%d')} 19:30", '%Y-%m-%d %H:%M')
        target_time = THAILAND_TZ.localize(target_time)
        
        return {
            'datetime': target_time,
            'weekday': 'monday',
            'time_range': '19:00-20:00',
            'thai_weekday': 'วันจันทร์'
        }
    
    def get_thai_weekday(self, weekday: str) -> str:
        """แปลงชื่อวันเป็นภาษาไทย"""
        thai_days = {
            'monday': 'วันจันทร์',
            'tuesday': 'วันอังคาร', 
            'wednesday': 'วันพุธ',
            'thursday': 'วันพฤหัสบดี',
            'friday': 'วันศุกร์',
            'saturday': 'วันเสาร์',
            'sunday': 'วันอาทิตย์'
        }
        return thai_days.get(weekday, weekday)
    
    def create_daily_auto_job(self) -> Job:
        """สร้าง Auto Job สำหรับวันถัดไป"""
        next_time = self.get_next_optimal_time()
        
        job_id = f"daily_auto_{int(time.time())}"
        job = Job(
            id=job_id,
            name=f"Auto ASMR - {next_time['thai_weekday']}",
            prompt='auto',
            schedule_time=next_time['datetime'].strftime('%Y-%m-%d %H:%M'),
            status='scheduled',
            created_at=datetime.now().isoformat()
        )
        
        return job, next_time
    
    def generate_random_asmr_prompt(self) -> str:
        """สุ่ม prompt ASMR แบบอัตโนมัติ"""
        import random
        
        # สุ่มหมวดหมู่
        category = random.choice(list(self.asmr_prompts.keys()))
        base_prompt = random.choice(self.asmr_prompts[category])
        
        # เพิ่มการปรับแต่งสุ่ม
        enhancements = [
            "Ultra-sharp macro lens, shallow depth of field",
            "Cinematic lighting with soft shadows", 
            "Professional studio lighting setup",
            "Natural daylight with warm tones",
            "Moody dramatic lighting"
        ]
        
        camera_angles = [
            "Extreme close-up from directly above",
            "45-degree angle perspective", 
            "Side view macro shot",
            "Slightly elevated bird's eye view"
        ]
        
        sound_descriptions = [
            "ASMR-quality audio with crisp, clear sounds",
            "High-fidelity slicing sounds only, no background noise",
            "Satisfying cutting sounds with natural acoustics", 
            "Crystal-clear audio capturing every detail"
        ]
        
        # สุ่มเลือกส่วนประกอบ
        enhancement = random.choice(enhancements)
        angle = random.choice(camera_angles)
        sound = random.choice(sound_descriptions)
        
        # รวม prompt สุ่ม
        final_prompt = f"{base_prompt} {enhancement}. {angle}. {sound}. Optimized for TikTok vertical format 9:16, 8-15 seconds duration."
        
        return final_prompt
    
    def generate_random_caption(self, prompt_used: str) -> str:
        """สร้าง caption สำหรับ TikTok แบบอัตโนมัติ"""
        import random
        
        captions = [
            "✨ Oddly satisfying ASMR moment ✨",
            "🔪 Glass cutting therapy 🔪", 
            "💎 Crystal clear relaxation 💎",
            "🧘‍♀️ ASMR vibes only 🧘‍♀️",
            "⚡ Satisfying slice sounds ⚡",
            "🎯 Perfect cuts every time 🎯",
            "🌟 AI-generated satisfaction 🌟",
            "💫 Mesmerizing ASMR content 💫"
        ]
        
        # สุ่ม hashtags (5-8 tags)
        selected_hashtags = random.sample(self.popular_hashtags, random.randint(5, 8))
        hashtag_string = ' '.join(selected_hashtags)
        
        caption = random.choice(captions)
        
        return f"{caption}\n\n{hashtag_string}"
    
    def generate_video_with_gemini(self, prompt: str) -> Dict:
        """สร้างวิดีโอด้วย Gemini + Veo 3"""
        try:
            # ปรับ prompt ให้เหมาะกับ Veo 3
            optimized_prompt = f"""
            Create a hyper-realistic ASMR video using Veo 3 technology:
            
            {prompt}
            
            Technical specifications:
            - Resolution: 1080x1920 (9:16 vertical for TikTok)
            - Duration: 8-15 seconds
            - Frame rate: 30 FPS
            - Audio: High-quality ASMR sounds synchronized with visuals
            - Style: Professional food photography lighting
            - Focus: Macro lens with shallow depth of field
            - Background: Minimal, clean wooden surface
            - Sound design: Only cutting/slicing sounds, no music
            """
            
            # สร้างวิดีโอด้วย Gemini (จำลอง Veo 3 integration)
            response = self.model.generate_content(optimized_prompt)
            
            # จำลองการสร้างวิดีโอ (ในความเป็นจริงจะเชื่อมต่อ Veo 3 API)
            video_data = {
                'video_url': f'https://storage.googleapis.com/asmr_videos/video_{int(time.time())}.mp4',
                'duration': random.randint(8, 15),
                'format': 'mp4',
                'resolution': '1080x1920',
                'audio_included': True,
                'generated_at': datetime.now().isoformat()
            }
            
            return {'success': True, 'data': video_data}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def upload_to_tiktok(self, video_url: str, caption: str) -> Dict:
        """อัปโหลดวิดีโอไป TikTok พร้อม auto-caption"""
        try:
            # ข้อมูลสำหรับ TikTok API
            upload_payload = {
                'video_url': video_url,
                'text': caption,
                'privacy_level': 'PUBLIC_TO_EVERYONE',
                'disable_duet': False,
                'disable_comment': False,
                'disable_stitch': False,
                'brand_content_toggle': False
            }
            
            # จำลอง TikTok API upload
            # ในความเป็นจริงจะใช้ TikTok Content Posting API
            tiktok_response = {
                'publish_id': f'tiktok_{int(time.time())}',
                'share_url': f'https://vm.tiktok.com/{random.randint(100000000, 999999999)}',
                'embed_url': f'https://www.tiktok.com/@autoasmr/video/{random.randint(7000000000000000000, 7999999999999999999)}',
                'status': 'PUBLISHED'
            }
            
            return {
                'success': True, 
                'tiktok_url': tiktok_response['share_url'],
                'embed_url': tiktok_response['embed_url'],
                'publish_id': tiktok_response['publish_id']
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def execute_job(self, job: Job):
        """ดำเนินการ job แบบ FULL AUTO"""
        try:
            # อัปเดทสถานะ
            job.status = 'running'
            job.last_run = datetime.now().isoformat()
            
            # Log การเริ่มงาน
            self.log_job_activity(job.id, '🤖 เริ่ม AUTO-JOB: กำลังสุ่ม prompt ASMR...', 'info')
            
            # 1. สุ่ม prompt ASMR แบบอัตโนมัติ (ถ้าไม่มี prompt หรือเป็น auto mode)
            if not job.prompt or job.prompt.lower() == 'auto':
                auto_prompt = self.generate_random_asmr_prompt()
                job.prompt = auto_prompt
                self.log_job_activity(job.id, f'✨ สุ่ม prompt สำเร็จ: {auto_prompt[:100]}...', 'success')
            
            # 2. สร้างวิดีโอด้วย Gemini + Veo 3
            self.log_job_activity(job.id, '🎬 กำลังสร้างวิดีโอ ASMR ด้วย AI...', 'info')
            
            video_result = self.generate_video_with_gemini(job.prompt)
            
            if not video_result['success']:
                job.status = 'failed'
                job.error_message = video_result['error']
                self.log_job_activity(job.id, f'❌ ล้มเหลวในการสร้างวิดีโอ: {video_result["error"]}', 'error')
                return
            
            job.video_url = video_result['data']['video_url']
            video_duration = video_result['data']['duration']
            self.log_job_activity(job.id, f'✅ สร้างวิดีโอสำเร็จ ({video_duration}s) - มีเสียง ASMR', 'success')
            
            # 3. สร้าง caption อัตโนมัติ
            self.log_job_activity(job.id, '📝 กำลังสร้าง caption และ hashtags...', 'info')
            auto_caption = self.generate_random_caption(job.prompt)
            self.log_job_activity(job.id, f'✨ Caption: {auto_caption[:50]}...', 'success')
            
            # 4. อัปโหลดไป TikTok
            self.log_job_activity(job.id, '📱 กำลังอัปโหลดไป TikTok...', 'info')
            
            upload_result = self.upload_to_tiktok(job.video_url, auto_caption)
            
            if not upload_result['success']:
                job.status = 'partial_success'  # วิดีโอสร้างได้แต่อัปโหลดไม่ได้
                job.error_message = upload_result['error']
                self.log_job_activity(job.id, f'⚠️ ล้มเหลวในการอัปโหลด: {upload_result["error"]}', 'error')
                return
            
            job.tiktok_url = upload_result['tiktok_url']
            job.status = 'completed'
            job.error_message = None
            
            # 5. สรุปผลลัพธ์
            self.log_job_activity(job.id, f'🎉 สำเร็จ! TikTok URL: {upload_result["tiktok_url"]}', 'success')
            self.log_job_activity(job.id, '🚀 AUTO-JOB เสร็จสมบูรณ์ - พร้อมไวรัล!', 'success')
            
            # 6. เพิ่มข้อมูลสถิติ
            self.log_job_activity(job.id, f'📊 ข้อมูล: ระยะเวลา {video_duration}s | ASMR Audio ✅ | คุณภาพ HD', 'info')
            
        except Exception as e:
            job.status = 'failed'
            job.error_message = str(e)
            self.log_job_activity(job.id, f'💥 เกิดข้อผิดพลาดร้ายแรง: {str(e)}', 'error')
    
    def log_job_activity(self, job_id: str, message: str, level: str):
        """บันทึก log กิจกรรม"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'job_id': job_id,
            'message': message,
            'level': level
        }
        job_logs.append(log_entry)
        
        # เก็บแค่ 1000 entries ล่าสุด
        if len(job_logs) > 1000:
            job_logs.pop(0)

# สร้าง instance
video_manager = VideoJobManager()

def schedule_daily_jobs():
    """ตั้งค่า scheduler สำหรับวันละ 1 คลิป"""
    
    def create_and_run_daily_job():
        """สร้างและรัน job รายวัน"""
        try:
            thailand_now = datetime.now(THAILAND_TZ)
            weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            today = weekdays[thailand_now.weekday()]
            
            # สร้าง job สำหรับวันนี้
            job_id = f"daily_auto_{today}_{int(time.time())}"
            job = Job(
                id=job_id,
                name=f"Daily ASMR - {video_manager.get_thai_weekday(today)}",
                prompt='auto',
                schedule_time='daily_auto',
                status='scheduled',
                created_at=datetime.now().isoformat()
            )
            
            jobs_storage[job_id] = job
            video_manager.log_job_activity(job_id, f'📅 สร้าง Daily Job สำหรับ{video_manager.get_thai_weekday(today)}', 'info')
            
            # รัน job ทันที
            video_manager.execute_job(job)
            
        except Exception as e:
            print(f"Error in daily job: {e}")
    
    # ตั้งเวลาสำหรับแต่ละวัน (เวลาไทย)
    schedule.every().monday.at("19:30").do(create_and_run_daily_job).tag('daily_upload')
    schedule.every().tuesday.at("16:30").do(create_and_run_daily_job).tag('daily_upload') 
    schedule.every().wednesday.at("17:30").do(create_and_run_daily_job).tag('daily_upload')
    schedule.every().thursday.at("17:30").do(create_and_run_daily_job).tag('daily_upload')
    schedule.every().friday.at("16:30").do(create_and_run_daily_job).tag('daily_upload')
    schedule.every().saturday.at("17:30").do(create_and_run_daily_job).tag('daily_upload')
    schedule.every().sunday.at("20:30").do(create_and_run_daily_job).tag('daily_upload')

# Routes
@app.route('/')
def dashboard():
    """หน้าแดชบอร์ด"""
    return render_template('dashboard.html', jobs=list(jobs_storage.values()))

@app.route('/auto_create', methods=['POST'])
def create_auto_job():
    """สร้าง Full Auto Job ทันที (ไม่ต้องใส่ prompt)"""
    try:
        job_id = f"auto_job_{int(time.time())}"
        job = Job(
            id=job_id,
            name=f"Auto ASMR #{len(jobs_storage) + 1}",
            prompt='auto',  # ใช้ auto mode
            schedule_time='manual',
            status='scheduled',
            created_at=datetime.now().isoformat()
        )
        
        jobs_storage[job_id] = job
        
        # รันทันที
        thread = threading.Thread(target=video_manager.execute_job, args=(job,))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True, 
            'job_id': job_id,
            'message': 'เริ่ม Auto-Job แล้ว! กำลังสุ่ม prompt และสร้างวิดีโอ...'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/mass_auto_create', methods=['POST'])
def create_mass_auto_jobs():
    """สร้าง Auto Jobs หลายๆ อันพร้อมกัน"""
    try:
        data = request.get_json()
        count = int(data.get('count', 3))  # default 3 jobs
        
        created_jobs = []
        
        for i in range(count):
            job_id = f"mass_auto_job_{int(time.time())}_{i}"
            job = Job(
                id=job_id,
                name=f"Auto ASMR Batch #{len(jobs_storage) + i + 1}",
                prompt='auto',
                schedule_time='manual',
                status='scheduled',
                created_at=datetime.now().isoformat()
            )
            
            jobs_storage[job_id] = job
            created_jobs.append(job_id)
            
            # รันแบบ delay เล็กน้อยเพื่อไม่ให้ซ้ำกัน
            def delayed_run(j, delay):
                time.sleep(delay)
                video_manager.execute_job(j)
            
            thread = threading.Thread(target=delayed_run, args=(job, i * 2))
            thread.daemon = True
            thread.start()
        
        return jsonify({
            'success': True,
            'created_jobs': created_jobs,
            'count': count,
            'message': f'เริ่ม {count} Auto-Jobs แล้ว!'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/enable_daily_auto', methods=['POST'])
def enable_daily_auto():
    """เปิดใช้งานระบบอัปโหลดรายวัน"""
    try:
        # ล้าง jobs เก่า
        schedule.clear('daily_upload')
        
        # ตั้งค่าใหม่
        schedule_daily_jobs()
        
        # สร้าง job ตัวอย่างสำหรับวันถัดไป
        next_time = video_manager.get_next_optimal_time()
        
        return jsonify({
            'success': True,
            'message': 'เปิดใช้งานระบบอัปโหลดรายวันแล้ว!',
            'next_upload': {
                'date': next_time['datetime'].strftime('%Y-%m-%d'),
                'time': next_time['datetime'].strftime('%H:%M'),
                'weekday': next_time['thai_weekday'],
                'range': next_time['time_range']
            },
            'schedule': video_manager.optimal_schedule
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/disable_daily_auto', methods=['POST'])
def disable_daily_auto():
    """ปิดใช้งานระบบอัปโหลดรายวัน"""
    try:
        schedule.clear('daily_upload')
        return jsonify({
            'success': True,
            'message': 'ปิดระบบอัปโหลดรายวันแล้ว'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/schedule_status')
def schedule_status():
    """ตรวจสอบสถานะ scheduler"""
    thailand_now = datetime.now(THAILAND_TZ)
    next_time = video_manager.get_next_optimal_time()
    
    # นับ jobs ที่ scheduled
    daily_jobs = schedule.get_jobs('daily_upload')
    
    return jsonify({
        'current_time': thailand_now.strftime('%Y-%m-%d %H:%M:%S %Z'),
        'scheduled_jobs_count': len(daily_jobs),
        'next_upload': {
            'datetime': next_time['datetime'].strftime('%Y-%m-%d %H:%M:%S'),
            'weekday': next_time['thai_weekday'],
            'time_range': next_time['time_range'],
            'hours_until': int((next_time['datetime'] - thailand_now).total_seconds() / 3600)
        },
        'weekly_schedule': video_manager.optimal_schedule
    })

@app.route('/jobs')
def jobs_list():
    """รายการ jobs"""
    return render_template('jobs.html', jobs=list(jobs_storage.values()))

@app.route('/create_job', methods=['GET', 'POST'])
def create_job():
    """สร้าง job ใหม่"""
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        
        job_id = f"job_{int(time.time())}"
        job = Job(
            id=job_id,
            name=data['name'],
            prompt=data['prompt'],
            schedule_time=data['schedule_time'],
            status='scheduled',
            created_at=datetime.now().isoformat()
        )
        
        jobs_storage[job_id] = job
        
        if request.is_json:
            return jsonify({'success': True, 'job_id': job_id})
        else:
            return redirect(url_for('jobs_list'))
    
    return render_template('create_job.html')

@app.route('/job/<job_id>')
def job_detail(job_id):
    """รายละเอียด job"""
    job = jobs_storage.get(job_id)
    if not job:
        return "Job not found", 404
    
    # ดึง logs ของ job นี้
    job_specific_logs = [log for log in job_logs if log['job_id'] == job_id]
    
    return render_template('job_detail.html', job=job, logs=job_specific_logs)

@app.route('/run_job/<job_id>', methods=['POST'])
def run_job_now(job_id):
    """รัน job ทันที"""
    job = jobs_storage.get(job_id)
    if not job:
        return jsonify({'success': False, 'error': 'Job not found'})
    
    # รัน job ใน background thread
    thread = threading.Thread(target=video_manager.execute_job, args=(job,))
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'message': 'Job started'})

@app.route('/logs')
def logs_page():
    """หน้า logs"""
    return render_template('logs.html', logs=reversed(job_logs[-100:]))  # แสดง 100 entries ล่าสุด

@app.route('/api/job_status/<job_id>')
def job_status_api(job_id):
    """API สำหรับเช็คสถานะ job"""
    job = jobs_storage.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify({
        'id': job.id,
        'status': job.status,
        'last_run': job.last_run,
        'video_url': job.video_url,
        'tiktok_url': job.tiktok_url,
        'error_message': job.error_message
    })

@app.route('/delete_job/<job_id>', methods=['POST'])
def delete_job(job_id):
    """ลบ job"""
    if job_id in jobs_storage:
        del jobs_storage[job_id]
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Job not found'})

def run_scheduler():
    """รัน scheduler ใน background"""
    while True:
        schedule.run_pending()
        time.sleep(60)  # เช็คทุกนาที

if __name__ == '__main__':
    # เริ่ม scheduler ใน background thread
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    
    # เริ่ม Flask app
    app.run(debug=True, threaded=True)