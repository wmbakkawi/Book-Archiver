import streamlit as st
import datetime
import os
import json
from google_services import authenticate_gcp, extract_text_from_image, upload_image_to_drive, add_row_to_sheet

# دعم النشر على Streamlit Cloud
if not os.path.exists("credentials.json") and "gcp_service_account_json" in st.secrets:
    try:
        creds_dict = json.loads(st.secrets["gcp_service_account_json"])
        with open("credentials.json", "w", encoding="utf-8") as f:
            json.dump(creds_dict, f)
    except:
        pass

st.set_page_config(page_title="أرشفة الكتب", page_icon="📚", layout="centered")

# --- محاولة المصادقة ---
vision_client, gc, drive = authenticate_gcp()

# تحذير إذا لم يتم العثور على credentials
if not all([gc, drive]):
    st.warning("⚠️ **تنبيه هام:** لم يتم العثور على ملف `credentials.json` الخاص بصلاحيات Google. التطبيق يعمل الآن في وضع الواجهة فقط ولن يتم حفظ أي بيانات. يرجى مراجعة ملف README للخطوات.")

# --- إعدادات المعرفات من الشريط الجانبي ---
with st.sidebar:
    st.header("إعدادات الربط مع جوجل ⚙️")
    st.info("قم بتعبئة هذه الخانات ليتمكن التطبيق من الحفظ في المكان الصحيح.")
    sheet_id = st.text_input("معرف جدول جوجل (Sheet ID):", help="الجزء المميز من رابط جدول الإكسل")
    title_folder_id = st.text_input("معرف مجلد صور غلاف الكتب:")
    shelf_folder_id = st.text_input("معرف مجلد صور الرفوف:")

st.title("نظام أرشفة الكتب الذكي 📚")
st.markdown("استخدم كاميرا جوالك لتسجيل ونقل بيانات الكتاب بسرعة إلى جداول جوجل.")

# تجهيز حالة البيانات المؤقتة (Session State) للحفظ المؤقت عند التحديث
if "extracted_lines" not in st.session_state:
    st.session_state.extracted_lines = []
if "title_image_bytes" not in st.session_state:
    st.session_state.title_image_bytes = None

# ---- القسم الأول: التقاط وتحليل الغلاف ----
st.subheader("1. استخراج البيانات من الغلاف")
title_image = st.camera_input("التقط صورة لغلاف الكتاب الداخلي أو الخارجي", key="title_cam")

if title_image:
    image_bytes = title_image.getvalue()
    # التحقق مما إذا كانت الصورة جديدة لكي لا نحلل نفس الصورة مرتين
    if st.session_state.title_image_bytes != image_bytes:
        st.session_state.title_image_bytes = image_bytes
        with st.spinner("جاري استخراج النصوص من الصورة... برجاء الانتظار"):
            lines = extract_text_from_image(vision_client, image_bytes)
            if lines:
                st.session_state.extracted_lines = lines
                st.success("✅ تمت قراءة النصوص من الصورة بنجاح! راجع الصناديق في الأسفل.")
            else:
                st.session_state.extracted_lines = ["لم يتم العثور على نص واضح"]
                st.error("❌ لم يتم الكشف عن نصوص كافية.")

st.divider()

# ---- القسم الثاني: التعديل والاعتماد ----
st.subheader("2. مراجعة بيانات الكتاب واعتمادها")

# جلب أول سطرين تم استخراجهما كاسم للمؤلف واسم للكتاب بناءً على طلبك
suggested_title = st.session_state.extracted_lines[0] if len(st.session_state.extracted_lines) > 0 else ""
suggested_author = st.session_state.extracted_lines[1] if len(st.session_state.extracted_lines) > 1 else ""

with st.form("book_form"):
    book_name = st.text_input("اسم الكتاب*", value=suggested_title)
    author = st.text_input("المؤلف*", value=suggested_author)
    
    col1, col2 = st.columns(2)
    with col1:
        publisher = st.text_input("الناشر")
    with col2:
        year = st.text_input("سنة النشر")
        
    copies = st.number_input("عدد النسخ*", min_value=1)
    
    col3, col4 = st.columns(2)
    with col3:
        cabinet_no = st.text_input("رقم الدولاب")
    with col4:
        shelf_no = st.text_input("رقم الرف")
    
    st.markdown("---")
    st.markdown("**صورة الرف (لإثبات الموقع)**")
    shelf_image = st.camera_input("التقط صورة لمكان الكتاب", key="shelf_cam")
    
    submitted = st.form_submit_button("إرسال واعتماد ✔️", use_container_width=True)
    
    if submitted:
        # التحققات (Validation)
        if not book_name:
            st.error("الرجاء إدخال اسم الكتاب على الأقل.")
        elif not sheet_id or not title_folder_id or not shelf_folder_id:
            st.error("الرجاء ملء المعرفات الخاصة بجدول ومجلدات صور Google في القائمة الجانبية.")
        elif not st.session_state.title_image_bytes:
            st.error("يرجى التقاط صورة الغلاف في الخطوة 1 أولاً، هي إلزامية.")
        else:
            with st.spinner("جاري رفع الصور للدرايف وحفظ البيانات في الجدول..."):
                try:
                    timestamp = datetime.datetime.now().strftime("%Y%md_%H%M%S")
                    
                    # 1. رفع صورة الغلاف
                    title_filename = f"{book_name}_Front_{timestamp}.jpg"
                    title_link = upload_image_to_drive(drive, st.session_state.title_image_bytes, title_filename, title_folder_id)
                    
                    # 2. رفع صورة الرف
                    shelf_link = ""
                    if shelf_image:
                        shelf_filename = f"{book_name}_Shelf_{timestamp}.jpg"
                        shelf_link = upload_image_to_drive(drive, shelf_image.getvalue(), shelf_filename, shelf_folder_id)
                    
                    # 3. إدخال السطر في Google Sheets
                    date_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    row_data = [
                        book_name, author, publisher, year, copies, 
                        cabinet_no, shelf_no, title_link, shelf_link, date_now
                    ]
                    
                    success = add_row_to_sheet(gc, sheet_id, row_data)
                    
                    if success:
                        st.success(f"🎉 تم حفظ الكتاب '{book_name}' بنجاح كمستند جديد!")
                        st.balloons()
                    else:
                        st.error("حدثت مشكلة أثناء محاولة إضافة البيانات إلى الجدول.")
                except Exception as e:
                    st.error(f"عذراً، حدث خطأ برمجي: {e}")
