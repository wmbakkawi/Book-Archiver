import os
import io
import json
import gspread
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

def authenticate_gcp():
    """
    يقوم بالتحقق من وجود ملف credentials.json وبدء خدمات Google.
    يعيد كائنات العملاء الثلاثة (vision, gspread, drive).
    """
    creds_path = "credentials.json"
    
    # 1. Vision API - تم إيقافه واستبداله بـ Tesseract
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

def extract_text_from_image(vision_client, image_bytes):
    """
    يأخذ الصورة المحولة ويحاول استخراج النص باستخدام Tesseract للتغلب على الفوترة.
    """
    try:
        import pytesseract
        from PIL import Image
        import io
        
        image = Image.open(io.BytesIO(image_bytes))
        # استخراج النص باللغتين العربية والإنجليزية
        text = pytesseract.image_to_string(image, lang='ara+eng')
        
        if text.strip():
            lines = text.split('\n')
            lines = [line.strip() for line in lines if line.strip()]
            return lines
            
    except Exception as e:
        return ["لم يتم استخراج النص آلياً (يرجى إدخال البيانات يدوياً).", "نأمل التحقق من تثبيت Tesseract."]

    return []

def upload_image_to_drive(drive_client, image_bytes, filename, folder_id):
    """
    يقوم برفع أجزاء الصورة وملفها إلى مجلد جوجل درايف محدد بالـ ID الخاص به.
    """
    if not drive_client:
        return "fake_link_no_credentials"
        
    file_metadata = {
        'title': filename,
        'parents': [{'id': folder_id}]
    }
    
    file = drive_client.CreateFile(file_metadata)
    
    # حفظ البايتات في ملف مؤقت لرفعه بفعالية
    temp_path = f"temp_{filename}"
    with open(temp_path, "wb") as f:
        f.write(image_bytes)
    
    file.SetContentFile(temp_path)
    file.Upload()
    
    # إعطاء صلاحية المشاهدة للرابط للجميع (اختياري، يسهل فتحه لاحقاً)
    file.InsertPermission({'type': 'anyone', 'value': 'anyone', 'role': 'reader'})
    
    os.remove(temp_path)
    return file['alternateLink']

def add_row_to_sheet(gspread_client, sheet_id, data_row):
    """
    يأخذ معرف شيت جوجل ويقوم بفتح الصفحة الأولى وكتابة السطر الجديد.
    """
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
