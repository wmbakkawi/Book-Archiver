import streamlit as st
import datetime
import os
import json
from google_services import authenticate_gcp, extract_text_with_gemini, upload_image_to_drive, add_row_to_sheet

def safe_get_secret(key, default=""):
    import os
    has_secrets = os.path.exists(".streamlit/secrets.toml") or os.path.exists(os.path.expanduser("~/.streamlit/secrets.toml"))
    if not has_secrets:
        return default
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default

# دعم النشر على Streamlit Cloud
if not os.path.exists("credentials.json"):
    gcp_json = safe_get_secret("gcp_service_account_json")
    if gcp_json:
        try:
            creds_dict = json.loads(gcp_json)
            with open("credentials.json", "w", encoding="utf-8") as f:
                json.dump(creds_dict, f)
        except Exception:
            pass

st.set_page_config(page_title="أرشفة الكتب الذكية", page_icon="📚", layout="centered")

# --- تنسيق الواجهة لضبط اتجاه النص العربي (Right-to-Left) ---
st.markdown(
    """
    <style>
    /* تغيير اتجاه كل العناصر ليكون من اليمين لليسار */
    .stApp, [data-testid="stSidebar"], [data-testid="stHeader"] {
        direction: rtl;
    }
    /* ضمان محاذاة كافة النصوص لليمين للحفاظ على التنسيق المفهوم */
    * {
        text-align: right;
    }
    /* استثناء الأزرار لتكون في المنتصف */
    .stButton > button {
        text-align: center !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --- محاولة المصادقة ---
_, gc, drive = authenticate_gcp()

# --- إعدادات المعرفات من الشريط الجانبي ---
with st.sidebar:
    st.header("إعدادات الربط ⚙️")
    gemini_key = st.text_input("Gemini API Key:", type="password", value=safe_get_secret("GEMINI_API_KEY"))
    sheet_id = st.text_input("معرف جدول جوجل (Sheet ID):", value="1jnKTmc5WzVMNtbid6JsBECd4xXIMLqaA0uwQSP5alXk")
    title_folder_id = st.text_input("معرف مجلد غلاف الكتب:", value="16kwd9Of6BAChHmN5FM3tWAyfZVuYPTPx")
    shelf_folder_id = st.text_input("معرف مجلد صور الرفوف:", value="18uijOw6CVEQVSH-dYjlUImri9ZR80MD1")
    
    if not gemini_key:
        st.warning("يرجى إدخال Gemini API Key لتفعيل ميزة التعرف التلقائي.")

st.title("نظام أرشفة الكتب الذكي 📚")

# تجهيز حالة البيانات المؤقتة
if "book_data" not in st.session_state:
    st.session_state.book_data = {"title": "", "author": "", "publisher": "", "year": ""}
if "title_image_bytes" not in st.session_state:
    st.session_state.title_image_bytes = None

# ---- القسم الأول: التقاط وتحليل الغلاف ----
st.subheader("1. استخراج البيانات من الغلاف")
col_cam1, col_up1 = st.columns(2)
with col_cam1:
    title_image_cam = st.camera_input("التقط صورة لغلاف الكتاب", key="title_cam")
with col_up1:
    title_image_up = st.file_uploader("أو ارفع صورة من الاستوديو", type=["jpg", "jpeg", "png"], key="title_up")

title_image = title_image_cam or title_image_up

if title_image:
    image_bytes = title_image.getvalue()
    if st.session_state.title_image_bytes != image_bytes:
        st.session_state.title_image_bytes = image_bytes
        with st.spinner("جاري تحليل الصورة باستخدام الذكاء الاصطناعي..."):
            extracted = extract_text_with_gemini(gemini_key, image_bytes)
            st.session_state.book_data = extracted
            if "فشل" in extracted.get("title", "") or "خطأ" in extracted.get("title", ""):
                 st.error("❌ " + extracted.get("title", "حدث خطأ غير معروف"))
            else:
                 st.success("✅ تم تحليل الغلاف بنجاح!")

st.divider()

# ---- القسم الثاني: التعديل والاعتماد ----
st.subheader("2. مراجعة بيانات الكتاب واعتمادها")

with st.form("book_form"):
    book_name = st.text_input("اسم الكتاب*", value=st.session_state.book_data.get("title", ""))
    author = st.text_input("المؤلف*", value=st.session_state.book_data.get("author", ""))
    
    col1, col2 = st.columns(2)
    with col1:
        publisher = st.text_input("الناشر", value=st.session_state.book_data.get("publisher", ""))
    with col2:
        year = st.text_input("سنة النشر", value=st.session_state.book_data.get("year", ""))
        
    copies = st.number_input("عدد النسخ*", min_value=1, value=1)
    
    col3, col4 = st.columns(2)
    with col3:
        cabinet_no = st.text_input("رقم الدولاب")
    with col4:
        shelf_no = st.text_input("رقم الرف")
    
    st.markdown("---")
    st.markdown("**صورة الرف (لإثبات الموقع)**")
    col_cam2, col_up2 = st.columns(2)
    with col_cam2:
        shelf_image_cam = st.camera_input("التقط صورة للرف", key="shelf_cam")
    with col_up2:
        shelf_image_up = st.file_uploader("أو ارفع صورة من الاستوديو", type=["jpg", "jpeg", "png"], key="shelf_up")
    
    shelf_image = shelf_image_cam or shelf_image_up
    
    submitted = st.form_submit_button("إرسال واعتماد ✔️", use_container_width=True)
    
    if submitted:
        if not book_name:
            st.error("الرجاء إدخال اسم الكتاب.")
        elif not all([sheet_id, title_folder_id, shelf_folder_id]):
            st.error("الرجاء إكمال إعدادات Google في القائمة الجانبية.")
        elif not st.session_state.title_image_bytes:
            st.error("يرجى التقاط صورة الغلاف أولاً.")
        else:
            with st.spinner("جاري حفظ البيانات..."):
                try:
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    
                    # 1. رفع صورة الغلاف
                    title_filename = f"{book_name}_Front_{timestamp}.jpg"
                    title_link = upload_image_to_drive(drive, st.session_state.title_image_bytes, title_filename, title_folder_id)
                    
                    # 2. رفع صورة الرف
                    shelf_link = ""
                    if shelf_image:
                        shelf_filename = f"{book_name}_Shelf_{timestamp}.jpg"
                        shelf_link = upload_image_to_drive(drive, shelf_image.getvalue(), shelf_filename, shelf_folder_id)
                    
                    # 3. حفظ السطر في Google Sheets
                    date_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    row_data = [
                        book_name, author, publisher, year, copies, 
                        cabinet_no, shelf_no, title_link, shelf_link, date_now
                    ]
                    
                    if add_row_to_sheet(gc, sheet_id, row_data):
                        st.success(f"🎉 تم حفظ الكتاب '{book_name}' بنجاح!")
                        st.balloons()
                        # إعادة تعيين البيانات بعد النجاح
                        st.session_state.book_data = {"title": "", "author": "", "publisher": "", "year": ""}
                    else:
                        st.error("فشل في إضافة السطر للجدول.")
                except Exception as e:
                    st.error(f"حدث خطأ: {e}")
