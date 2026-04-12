import os
import io
import json
import gspread
import google.generativeai as genai
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from PIL import Image

def authenticate_gcp():
    creds_path = "credentials.json"
    
    # 1. إعداد Gemini API
    # سنقوم بجلب المفتاح من متغيرات البيئة أو st.secrets في app.py لاحقاً
    vision_client = None 

    # 2. Gspread
    if os.path.exists(creds_path):
        gc = gspread.service_account(filename=creds_path)
    else:
        gc = None

    # 3. PyDrive2
    if os.path.exists(creds_path):
        with open(creds_path, 'r', encoding='utf-8') as f:
            creds_data = json.load(f)
            client_email = creds_data.get("client_email", "")
            
        gauth = GoogleAuth()
        gauth.settings['client_config_backend'] = "service"
        gauth.settings['service_config'] = {
            "client_json_file_path": creds_path,
            "client_user_email": client_email,
        }
        gauth.ServiceAuth()
        drive = GoogleDrive(gauth)
    else:
        drive = None

    return vision_client, gc, drive

def extract_text_with_gemini(api_key, image_bytes):
    """استخراج بيانات الكتاب باستخدام Gemini 1.5 Flash"""
    if not api_key:
        return {"title": "خطأ: مفتاح Gemini مفقود", "author": ""}

    try:
        genai.configure(api_key=api_key)
        
        # تحويل الصورة لتنسيق يفهمه Gemini
        image = Image.open(io.BytesIO(image_bytes))
        
        prompt = """
        أنت مساعد متخصص في أرشفة الكتب. من خلال صورة غلاف الكتاب المرفقة، استخرج المعلومات التالية بدقة وباللغة العربية:
        1. اسم الكتاب (title)
        2. اسم المؤلف (author)
        3. دار النشر (publisher) - إن وجد
        4. سنة النشر (year) - إن وجد
        
        قم بالرد بصيغة JSON فقط كالتالي:
        {"title": "...", "author": "...", "publisher": "...", "year": "..."}
        إذا لم تجد معلومة، اترك قيمتها نصاً فارغاً.
        """
        
        # تجربة أحدث النماذج المتاحة تدريجياً لتجنب مشاكل حذف النماذج القديمة
        models_to_try = ['gemini-3.1-flash', 'gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash-latest']
        
        last_error = ""
        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(
                    [prompt, image],
                    generation_config={"response_mime_type": "application/json"}
                )
                data = json.loads(response.text)
                return data
            except Exception as e:
                err_msg = str(e)
                if "404" in err_msg or "not found" in err_msg:
                    last_error = err_msg
                    continue # Try the next model
                else:
                    raise e # Some other API error (e.g. invalid key)
                    
        raise Exception(f"النماذج غير مدعومة حالياً. آخر خطأ: {last_error}")
        
    except Exception as e:
        err_msg = str(e)
        print(f"Gemini Error: {err_msg}")
        return {"title": f"فشل الاستخراج: {err_msg}", "author": ""}

def upload_image_to_drive(drive_client, image_bytes, filename, folder_id):
    if not drive_client:
        return "fake_link_no_credentials"
        
    file_metadata = {
        'title': filename,
        'parents': [{'id': folder_id}]
    }
    
    file = drive_client.CreateFile(file_metadata)
    
    # تحويل الصورة إلى ملف مؤقت للرفع
    temp_path = f"temp_{filename}"
    with open(temp_path, "wb") as f:
        f.write(image_bytes)
    
    file.SetContentFile(temp_path)
    file.Upload()
    
    # جعل الصورة قابلة للعرض (اختياري)
    file.InsertPermission({'type': 'anyone', 'value': 'anyone', 'role': 'reader'})
    
    os.remove(temp_path)
    return file['alternateLink']

def add_row_to_sheet(gspread_client, sheet_id, data_row):
    if not gspread_client:
        return False
        
    try:
        sh = gspread_client.open_by_key(sheet_id)
        worksheet = sh.sheet1 
        worksheet.append_row(data_row)
        return True
    except Exception as e:
        print(f"Error appending row: {e}")
        return False
