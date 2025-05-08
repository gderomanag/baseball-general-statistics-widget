"""
Baseball Performance Widget
---------------------------
This Streamlit app pulls player statistics from the Pointstreak API for a given baseball season and displays
batting, fielding, and pitching data with filtering capabilities. The user can generate and download a PDF
report summarizing the top filtered results.

Main Features:
- Interactive UI with team/player/sort filters for batting, fielding, and pitching.
- Pulls and cleans data from Pointstreak's public API.
- Displays data tables using Streamlit and generates a stylized PDF report.
- Handles time zones and ensures report filenames are timestamped appropriately.

Dependencies:
- streamlit, pandas, requests, reportlab, zoneinfo
"""

# -------------------------
# Imports and Configuration
# -------------------------

# Core libraries

import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from reportlab.lib.pagesizes import LETTER
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import LETTER, landscape
import os
from io import BytesIO
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# -------------------
# Pointstreak API Setup
# -------------------

load_dotenv()

# Get API key from environment
API_KEY = os.getenv("API_KEY")
BASE_URL = "https://api.pointstreak.com"
HEADERS = {"apikey": API_KEY}
SEASON_ID = 34102

# -------------------
# API Fetch Function
# -------------------

def fetch(endpoint):
    url = f"{BASE_URL}/{endpoint}"
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if response.status_code == 404:
            print(f"404 Not Found: {url}")
        else:
            print(f"Error fetching {url}: {e}")
        return {}


# ---------------------------
# Data Retrieval Functions
# ---------------------------

def get_batting_stats(season_id):
    data = fetch(f"baseball/season/stats/{season_id}/json")
    return pd.DataFrame(data.get("stats", {}).get("batting", {}).get("player", []))

def get_pitching_stats(season_id):
    data = fetch(f"baseball/season/stats/{season_id}/json")
    return pd.DataFrame(data.get("stats", {}).get("pitching", {}).get("player", []))

def get_fielding_stats(season_id):
    data = fetch(f"baseball/season/fieldingleaders/{season_id}/json")
    players = []
    for position in data.get("stats", {}).get("position", []):
        player_list = position.get("player", [])
        if isinstance(player_list, list):
            for player in player_list:
                player["position"] = position.get("position")
                players.append(player)
    return pd.DataFrame(players)


# ------------------------
# Data Cleaning Functions
# ------------------------

def clean_batting_df(df):
    """Clean and structure batting stats DataFrame."""
    if "teamname" in df.columns:
        df["teamname"] = df["teamname"].apply(lambda x: x.get("$t") if isinstance(x, dict) else x)
    df = df.drop(columns=[col for col in ["playerlinkid", "playerid", "firstname", "lastname"] if col in df.columns])
    rename_map = {"playername": "PLAYER", "teamname": "TEAM", "jersey": "JERSEY", "position": "P"}
    df = df.rename(columns=rename_map)
    df.columns = [rename_map.get(col, col.upper()) for col in df.columns]
    numeric_cols = ["AVG", "AB", "RUNS", "HITS", "HR", "RBI", "BB", "HP", "SO", "SF", "SB", "DP", "BIB", "TRIB", "OBP", "SLG"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    order = ["PLAYER", "JERSEY", "TEAM", "P", "AVG", "AB", "RUNS", "HITS", "HR", "RBI", "BB", "HP", "SO", "SF", "SB", "DP"]
    return df[[col for col in order if col in df.columns] + [col for col in df.columns if col not in order]]

def clean_pitching_df(df):
    """Clean and structure pitching stats DataFrame."""
    if "teamname" in df.columns:
        df["teamname"] = df["teamname"].apply(lambda x: x.get("$t") if isinstance(x, dict) else x)
    df = df.drop(columns=[col for col in ["playerlinkid", "playerid", "firstname", "lastname", "oobp", "oslg", "oavg"] if col in df.columns])
    rename_map = {"playername": "PLAYER", "teamname": "TEAM", "jersey": "JERSEY", "games": "G"}
    df = df.rename(columns=rename_map)
    df.columns = [rename_map.get(col, col.upper()) for col in df.columns]
    numeric_cols = ["ERA", "G", "GS", "CG", "CGL", "IP", "HITS", "RUNS", "ER", "BB", "SO", "SV", "BSV", "WINS", "LOSSES", "BF", "SHO"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    order = ["PLAYER", "JERSEY", "TEAM", "ERA", "G", "GS", "CG", "CGL", "IP", "HITS", "RUNS", "ER", "BB", "SO", "WINS", "LOSSES", "SV", "BSV"]
    return df[[col for col in order if col in df.columns] + [col for col in df.columns if col not in order]]

def clean_fielding_df(df):
    """Clean and structure fielding stats DataFrame."""
    if "teamname" in df.columns:
        df["teamname"] = df["teamname"].apply(lambda x: x.get("$t") if isinstance(x, dict) else x)
    df = df.drop(columns=[col for col in ["playerlinkid"] if col in df.columns])
    rename_map = {"name": "PLAYER", "jersey": "JERSEY", "teamname": "TEAM", "position": "P"}
    df = df.rename(columns=rename_map)
    df.columns = [rename_map.get(col, col.upper()) for col in df.columns]
    numeric_cols = ["FPCT", "GP", "PO", "A"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    order = ["PLAYER", "JERSEY", "TEAM", "P", "FPCT", "GP", "PO", "A"]
    return df[[col for col in order if col in df.columns] + [col for col in df.columns if col not in order]]

# -----------------------
# PDF Generation Function
# -----------------------


def generate_pdf(batting_df, fielding_df, pitching_df, batting_filters, fielding_filters, pitching_filters):
    """
    Generate a PDF report of the filtered data tables.

    Args:
        batting_df (DataFrame), fielding_df (DataFrame), pitching_df (DataFrame): Cleaned stat data.
        batting_filters, fielding_filters, pitching_filters: Tuple of (team, player, sort) for display.

    Returns:
        BytesIO: In-memory PDF document stream.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(LETTER))
    elements = []
    styles = getSampleStyleSheet()
    custom_title_style = ParagraphStyle(name="CustomTitle", parent=styles['Title'], textColor=colors.HexColor("#000c66"), fontSize=14, alignment=1)
    filter_style = ParagraphStyle(name="FilterStyle", parent=styles['Normal'], textColor=colors.HexColor("#c62127"), fontSize=8, alignment=1)
    date_style = ParagraphStyle(name="DateStyle", parent=styles['Normal'], textColor=colors.HexColor("#000c66"), fontSize=7, alignment=1)

    # Add header
    if os.path.exists("WidgetHeader.png"):
        elements.append(Image("WidgetHeader.png", width=500, height=80))
        elements.append(Spacer(1, 12))

    # Add current date and time
    now = datetime.now(ZoneInfo("America/New_York"))
    report_date = now.strftime("Report Date: %B %d, %Y at %I:%M %p")
    elements.append(Paragraph(report_date, date_style))
    elements.append(Spacer(1, 24))

    # Helper function to add a table section
    def add_title_and_table(title, df, filters):
        team, player, sort = filters
        elements.append(Paragraph(title, custom_title_style))
        elements.append(Spacer(1, 6))
        filter_text = f"Filters: Team = {team}, Player = {player}, Sort = {sort}"
        if title.startswith("Batting") and batting_position:
            filter_text += f", Position = {batting_position}"
        elif title.startswith("Fielding") and fielding_position:
            filter_text += f", Position = {fielding_position}"
        elements.append(Paragraph(filter_text, filter_style))
        elements.append(Spacer(1, 12))
        data = [df.columns.tolist()] + df.values.tolist()
        data = [[str(cell) for cell in row] for row in data]
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0072eb")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (1, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),     # header row
            ('FONTSIZE', (1, 1), (-1, -1), 8),    # table body
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (1, 1), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.black),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 24))

    add_title_and_table("Batting Stats", batting_df, batting_filters)
    add_title_and_table("Fielding Stats", fielding_df, fielding_filters)
    add_title_and_table("Pitching Stats", pitching_df, pitching_filters)

    doc.build(elements)
    buffer.seek(0)
    return buffer


# --------------------
# Data Load & Cleaning
# --------------------

batting_data = clean_batting_df(get_batting_stats(SEASON_ID))
pitching_data = clean_pitching_df(get_pitching_stats(SEASON_ID))
fielding_data = clean_fielding_df(get_fielding_stats(SEASON_ID))

# -----------------------
# Streamlit UI Definition
# -----------------------

# Configure Streamlit page
st.set_page_config(page_title="Baseball Performance Widget", layout="wide")
PRIMARY_COLOR = "#c62127"
SECONDARY_COLOR = "#000c66"
TERTIARY_COLOR = "#0072eb"

# Display app title and subtitle
st.markdown(
    f"""
    <div style='background-color:{SECONDARY_COLOR}; padding:10px; border-radius:10px;'>
    <h1 style='color:{TERTIARY_COLOR}; text-align:center;'>Baseball Performance Widget</h1>
    <p style='color:white; text-align:center;'>Filter and View Key Player Statistics for Batting, Fielding, and Pitching</p>
    </div>
    """,
    unsafe_allow_html=True
)

# --------------------------
# Sidebar Filters (3 columns)
# --------------------------

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Batting Stats")
    batting_team = st.selectbox("Select Team (Batting)", ["All"] + sorted(batting_data["TEAM"].unique()))
    batting_player = st.selectbox("Select Player (Batting)", ["All"] + sorted(batting_data["PLAYER"].unique()))
    batting_position = st.selectbox("Select Position (Batting)", ["All"] + sorted(batting_data["P"].dropna().unique()))
    batting_sort = st.selectbox("Sort By (Batting)", ["None"] + [col for col in batting_data.columns if pd.api.types.is_numeric_dtype(batting_data[col])])

with col2:
    st.subheader("Fielding Stats")
    fielding_team = st.selectbox("Select Team (Fielding)", ["All"] + sorted(fielding_data["TEAM"].unique()))
    fielding_player = st.selectbox("Select Player (Fielding)", ["All"] + sorted(fielding_data["PLAYER"].unique()))
    fielding_position = st.selectbox("Select Position (Fielding)", ["All"] + sorted(fielding_data["P"].dropna().unique()))
    fielding_sort = st.selectbox("Sort By (Fielding)", ["None"] + [col for col in fielding_data.columns if pd.api.types.is_numeric_dtype(fielding_data[col])])

with col3:
    st.subheader("Pitching Stats")
    pitching_team = st.selectbox("Select Team (Pitching)", ["All"] + sorted(pitching_data["TEAM"].unique()))
    pitching_player = st.selectbox("Select Player (Pitching)", ["All"] + sorted(pitching_data["PLAYER"].unique()))
    pitching_sort = st.selectbox("Sort By (Pitching)", ["None"] + [col for col in pitching_data.columns if pd.api.types.is_numeric_dtype(pitching_data[col])])
    st.markdown("<div style='height: 85px;'></div>", unsafe_allow_html=True)

# --------------------
# Filter the datasets
# --------------------

batting_filtered = batting_data.copy()
if batting_team != "All":
    batting_filtered = batting_filtered[batting_filtered["TEAM"] == batting_team]
if batting_player != "All":
    batting_filtered = batting_filtered[batting_filtered["PLAYER"] == batting_player]
if batting_position != "All":
    batting_filtered = batting_filtered[batting_filtered["P"] == batting_position]
if batting_sort != "None":
    batting_filtered = batting_filtered.sort_values(by=batting_sort, ascending=False)

fielding_filtered = fielding_data.copy()
if fielding_team != "All":
    fielding_filtered = fielding_filtered[fielding_filtered["TEAM"] == fielding_team]
if fielding_player != "All":
    fielding_filtered = fielding_filtered[fielding_filtered["PLAYER"] == fielding_player]
if fielding_position != "All":
    fielding_filtered = fielding_filtered[fielding_filtered["P"] == fielding_position]
if fielding_sort != "None":
    fielding_filtered = fielding_filtered.sort_values(by=fielding_sort, ascending=False)

pitching_filtered = pitching_data.copy()
if pitching_team != "All":
    pitching_filtered = pitching_filtered[pitching_filtered["TEAM"] == pitching_team]
if pitching_player != "All":
    pitching_filtered = pitching_filtered[pitching_filtered["PLAYER"] == pitching_player]
if pitching_sort != "None":
    pitching_filtered = pitching_filtered.sort_values(by=pitching_sort, ascending=False)

# --------------------
# Download PDF Report
# --------------------

now = datetime.now(ZoneInfo("America/New_York"))
now_str = now.strftime("%Y-%m-%d_%H-%M")

st.download_button(
    label="🖨️ Generate and Download PDF",
    data=generate_pdf(
        batting_filtered, fielding_filtered, pitching_filtered,
        batting_filters=(batting_team, batting_player, batting_sort),
        fielding_filters=(fielding_team, fielding_player, fielding_sort),
        pitching_filters=(pitching_team, pitching_player, pitching_sort)
    ),
    file_name=f"stats_report_{now_str}.pdf",
    mime="application/pdf"
)

# ---------------------
# Display Filtered Tables
# ---------------------

col1.dataframe(batting_filtered, use_container_width=True)
col2.dataframe(fielding_filtered, use_container_width=True)
col3.dataframe(pitching_filtered, use_container_width=True)
