import streamlit as st
from app.engine import Conversation
from app.feedback import save_session

st.set_page_config(page_title="דניאל - אורן כהן גרופ", page_icon="🏢")

if "conv" not in st.session_state:
    st.session_state.conv = Conversation()

st.title('🏢 דניאל - סוכן הנדל"ן שלך')

# ניהול מצב דירוג בזיכרון
if "show_rating" not in st.session_state:
    st.session_state.show_rating = False

# הצגת היסטוריית השיחה
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# תפריט צדדי לסיום שיחה
if st.sidebar.button("סיום שיחה ואימון הבוט"):
    # שמירה ל-JSON לפני איפוס
    save_session(
        transcript=st.session_state.messages,
        bot_level=st.session_state.conv.last_turn.stage if st.session_state.conv.last_turn else "unknown",
        bot_score=0.0, # ניתן לעדכן בהמשך לפי הצורך
        profile=st.session_state.conv.profile.model_dump()
    )
    st.session_state.show_rating = True

# ממשק דירוג (מופיע רק אחרי לחיצה על כפתור סיום)
if st.session_state.show_rating:
    st.divider()
    st.write("### סיום שיחה - דרג את הליד (אימון הבוט):")
    col1, col2, col3 = st.columns(3)
    
    if col1.button("🔴 רציני מאוד (High)"):
        st.success("הליד סומן כאדום (High) - נשמר במאגר האימון!")
        st.session_state.show_rating = False
        st.session_state.messages = [] # איפוס לשיחה הבאה
        st.rerun()

    if col2.button("🟠 בינוני (Medium)"):
        st.info("הליד סומן ככתום (Medium).")
        st.session_state.show_rating = False
        st.rerun()

    if col3.button("🟢 לא רציני (Low)"):
        st.warning("הליד סומן כירוק (Low).")
        st.session_state.show_rating = False
        st.rerun()

# קלט מהמשתמש
if prompt := st.chat_input("כתוב משהו לדניאל..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            turn, score = st.session_state.conv.send(prompt)
            st.session_state.conv.last_turn = turn # שמירת המצב האחרון
            response = turn.reply
            
            st.markdown(response)
            st.caption(f"סיווג נוכחי: {score.level} | ציון: {score.score:.2f}")
            
            st.session_state.messages.append({"role": "assistant", "content": response})
        except Exception as e:
            st.error(f"אופס, קרתה שגיאה: {e}")