import streamlit as st
import pandas as pd

if "fetched_records_list" not in st.session_state:
    st.session_state.fetched_records_list = None

animal_text = st.text_area("input", "123456789012\n123456789013")

if st.button("fetch"):
    records = [{"animal_no": "123", "grade": "1++"}, {"animal_no": "456", "grade": "1+"}]
    st.session_state.fetched_records_list = records
    st.rerun()

if st.session_state.fetched_records_list is not None:
    st.write("data")
    df = pd.DataFrame(st.session_state.fetched_records_list)
    edited = st.data_editor(df, num_rows="dynamic")
    if st.button("save"):
        st.session_state.fetched_records_list = None
        st.rerun()
