import streamlit as st
import requests
from datetime import datetime, date, time, timedelta

st.set_page_config(page_title="Psych Appointments", page_icon="🧠", layout="centered")

st.title("🧠 Psych Appointment — Streamlit Frontend")

# Config
api_base = st.sidebar.text_input("API Base URL", "http://localhost:8000")
st.sidebar.markdown("Run the API with: `uvicorn main:app --reload`")

def api_get(path, **params):
    r = requests.get(f"{api_base}{path}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def api_post(path, payload):
    r = requests.post(f"{api_base}{path}", json=payload, timeout=15)
    r.raise_for_status()
    return r.json()

def api_put(path, payload):
    r = requests.put(f"{api_base}{path}", json=payload, timeout=15)
    r.raise_for_status()
    return r.json()

def api_delete(path):
    r = requests.delete(f"{api_base}{path}", timeout=15)
    r.raise_for_status()
    return r.json()

def load_blocks(date_str):
    try:
        blocks = api_get("/availability/blocks", date=date_str)
        st.session_state.blocks = blocks
    except requests.HTTPError as e:
        try:
            st.error(e.response.json().get("detail", str(e)))
        except Exception:
            st.error(f"API returned an error: {e.response.text}")
    except Exception as e:
        st.error(f"Failed to load blocks: {e}")

if "blocks" not in st.session_state:
    st.session_state.blocks = []
if "appointments" not in st.session_state:
    st.session_state.appointments = []

with st.expander("Health / Office hours", expanded=False):
    try:
        st.json(api_get("/health"))
    except Exception as e:
        st.error(f"API not reachable: {e}")

tab1, tab2, tab3, tab4 = st.tabs(["Book", "Manage", "Availability", "Admin (Blocks)"])

with tab1:
    st.subheader("Book an appointment")
    name = st.text_input("Patient name")
    phone = st.text_input("Phone (unique ID)", placeholder="+92300...")
    note = st.text_area("Note (optional)")

    day = st.date_input("Date", value=date.today())
    hour = st.time_input("Start time", value=time(10, 0), step=1800)  # 30-min step

    if st.button("Book 30-min slot"):
        if not phone:
            st.warning("Phone is required")
        else:
            try:
                start_iso = datetime.combine(day, hour).isoformat(timespec="minutes")
                res = api_post("/appointments/book", {"phone": phone, "start_time": start_iso, "note": note})
                st.success("Booked!")
                st.json(res)
            except requests.HTTPError as e:
                try:
                    st.error(e.response.json().get("detail", str(e)))
                except Exception:
                    st.error(f"API returned an error: {e.response.text}")

with tab2:
    st.subheader("Manage my appointments")
    p2 = st.text_input("Phone to lookup", key="lookup_phone", placeholder="+92300...")
    
    if st.button("Load appointments"):
        if p2:
            try:
                appts = api_get(f"/patients/{p2}/appointments")
                st.session_state.appointments = appts
                if not appts:
                    st.info("No appointments found for this phone number.")
                else:
                    for a in appts:
                        col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
                        with col1:
                            st.write(f"ID: {a['id']}")
                        with col2:
                            st.write(f"Start: {a['start_time']}")
                        with col3:
                            st.write(f"End: {a['end_time']}")
                        with col4:
                            if st.button("Delete", key=f"del_{a['id']}"):
                                try:
                                    api_delete(f"/appointments/{a['id']}")
                                    st.success(f"Deleted appointment {a['id']}.")
                                    st.rerun()  # Corrected from experimental_rerun
                                except requests.HTTPError as e:
                                    try:
                                        st.error(e.response.json().get("detail", str(e)))
                                    except Exception:
                                        st.error(f"API returned an error: {e.response.text}")
            except requests.HTTPError as e:
                try:
                    st.error(e.response.json().get("detail", str(e)))
                except Exception:
                    st.error(f"API returned an error: {e.response.text}")
        else:
            st.warning("Please enter a phone number.")
            st.session_state.appointments = []

    st.markdown("---")
    st.subheader("Reschedule")
    
    appt_ids = [appt['id'] for appt in st.session_state.appointments]
    
    if appt_ids:
        selected_appt_id = st.selectbox("Select Appointment ID to update", options=appt_ids, key="resch_id_select")
        
        selected_appt_data = next((a for a in st.session_state.appointments if a['id'] == selected_appt_id), None)
        if selected_appt_data:
            initial_datetime = datetime.fromisoformat(selected_appt_data['start_time'])
            new_day = st.date_input("New date", value=initial_datetime.date(), key="newdate")
            new_time = st.time_input("New time", value=initial_datetime.time(), step=1800, key="newtime")
        else:
            new_day = st.date_input("New date", value=date.today(), key="newdate")
            new_time = st.time_input("New time", value=time(11, 0), step=1800, key="newtime")
    
        if st.button("Update time"):
            try:
                new_iso = datetime.combine(new_day, new_time).isoformat(timespec="minutes")
                res = api_put(f"/appointments/{selected_appt_id}", {"new_start_time": new_iso})
                st.success("Appointment updated successfully!")
                st.json(res)
                st.session_state.appointments = []
            except requests.HTTPError as e:
                try:
                    st.error(e.response.json().get("detail", str(e)))
                except Exception:
                    st.error(f"API returned an error: {e.response.text}")
    else:
        st.info("Load a patient's appointments first to see options here.")

with tab3:
    st.subheader("Check availability")
    mode = st.radio("Pick by", ["Date", "Day of week"], horizontal=True)
    
    if mode == "Date":
        day3 = st.date_input("Date to check", value=date.today(), key="availdate")
        if st.button("Show slots"):
            try:
                res = api_get("/availability", date=day3.isoformat())
                slots = res.get("slots", [])
                if not slots:
                    st.warning("No free slots.")
                else:
                    for s in slots:
                        st.write(f"- {s['label']} ({s['start']} → {s['end']})")
            except requests.HTTPError as e:
                try:
                    st.error(e.response.json().get("detail", str(e)))
                except Exception:
                    st.error(f"API returned an error: {e.response.text}")
    else:
        dow = st.selectbox("Day of week", ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        ref = st.date_input("Reference date (optional)", value=date.today())
        if st.button("Show next slots for that weekday"):
            try:
                res = api_get("/availability", day_of_week=dow.lower(), ref_date=ref.isoformat())
                slots = res.get("slots", [])
                st.caption(f"Date resolved to: {res.get('date')}")
                if not slots:
                    st.warning("No free slots.")
                else:
                    for s in slots:
                        st.write(f"- {s['label']} ({s['start']} → {s['end']})")
            except requests.HTTPError as e:
                try:
                    st.error(e.response.json().get("detail", str(e)))
                except Exception:
                    st.error(f"API returned an error: {e.response.text}")

with tab4:
    st.subheader("Admin: Block time")
    bday = st.date_input("Block date", value=date.today(), key="bdate")
    bstart = st.time_input("Start", value=time(13, 30), step=1800, key="bstart")
    bend = st.time_input("End", value=time(15, 30), step=1800, key="bend")
    reason = st.text_input("Reason", placeholder="Lunch, offsite, etc.")
    
    if st.button("Add block"):
        try:
            s_iso = datetime.combine(bday, bstart).isoformat(timespec="minutes")
            e_iso = datetime.combine(bday, bend).isoformat(timespec="minutes")
            res = api_post("/availability/block", {"start_time": s_iso, "end_time": e_iso, "reason": reason})
            st.success("Block added")
            st.json(res)
            # Re-fetch blocks for the current day to show the updated list
            load_blocks(bday.isoformat())
        except requests.HTTPError as e:
            try:
                st.error(e.response.json().get("detail", str(e)))
            except Exception:
                st.error(f"API returned an error: {e.response.text}")

    st.markdown("---")
    st.subheader("View / Remove blocks")
    bday2 = st.date_input("For date", value=date.today(), key="bdate2")
    
    if st.button("Load blocks"):
        load_blocks(bday2.isoformat())

    if st.session_state.blocks:
        for b in st.session_state.blocks:
            col1, col2, col3, col4 = st.columns([2, 3, 3, 2])
            with col1:
                st.write(f"ID: {b['id']}")
            with col2:
                st.write(f"Start: {b['start_time']}")
            with col3:
                st.write(f"End: {b['end_time']}")
            with col4:
                if st.button("Delete", key=f"blk_{b['id']}"):
                    try:
                        api_delete(f"/availability/blocks/{b['id']}")
                        st.success(f"Deleted block {b['id']}")
                        # Re-fetch blocks to update the displayed list
                        load_blocks(bday2.isoformat())
                        st.rerun() # Corrected from experimental_rerun
                    except requests.HTTPError as e:
                        try:
                            st.error(e.response.json().get("detail", str(e)))
                        except Exception:
                            st.error(f"API returned an error: {e.response.text}")
    else:
        st.info("No blocks loaded for this date.")