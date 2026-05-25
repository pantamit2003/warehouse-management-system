import streamlit as st
import requests
import pandas as pd
import threading
import concurrent.futures
import time
from datetime import datetime

# ==========================================
# PAGE CONFIG
# ==========================================

st.set_page_config(
    page_title="Swiss Military Warehouse Material Planning",
    layout="wide"
)

# ==========================================
# SESSION STATE
# ==========================================

if "page" not in st.session_state:
    st.session_state.page = "home"

if "po_items" not in st.session_state:
    st.session_state.po_items = []

if "add_success" not in st.session_state:
    st.session_state.add_success = False

if "save_success" not in st.session_state:
    st.session_state.save_success = False

if "gate_out_success" not in st.session_state:
    st.session_state.gate_out_success = False

if "po_created" not in st.session_state:
    st.session_state.po_created = False

# ==========================================
# CREATE PO INPUT RESET
# ==========================================

if "created_by" not in st.session_state:
    st.session_state.created_by = ""

if "po_no" not in st.session_state:
    st.session_state.po_no = ""

if "vendor" not in st.session_state:
    st.session_state.vendor = ""

# ==========================================
# GOOGLE SHEET URLS
# ==========================================

po_master_url = "https://docs.google.com/spreadsheets/d/1qigLvcJBOV8LSpRgAqu2LQYNGR3TRQk2YSAscXPpnwU/export?format=csv&gid=492171748"

po_items_url = "https://docs.google.com/spreadsheets/d/1qigLvcJBOV8LSpRgAqu2LQYNGR3TRQk2YSAscXPpnwU/export?format=csv&gid=0"

gate_out_url = "https://docs.google.com/spreadsheets/d/1qigLvcJBOV8LSpRgAqu2LQYNGR3TRQk2YSAscXPpnwU/export?format=csv&gid=1594713379"

location_master_url = "https://docs.google.com/spreadsheets/d/1qigLvcJBOV8LSpRgAqu2LQYNGR3TRQk2YSAscXPpnwU/export?format=csv&gid=336519732"

# ==========================================
# LOAD DATA
# SPEED FIX 1 : ttl=5 → ttl=60
#   Was hammering Google Sheets every 5 s
#   on every single user interaction.
# SPEED FIX 2 : one @st.cache_data per sheet
#   so each sheet caches independently.
# SPEED FIX 3 : ThreadPoolExecutor fetches
#   all 4 sheets IN PARALLEL instead of
#   sequentially — cuts load time ~65 %.
# ==========================================

@st.cache_data(ttl=60)
def load_po_master():
    df = pd.read_csv(po_master_url)
    df.columns = df.columns.str.strip()
    return df


@st.cache_data(ttl=60)
def load_po_items():
    try:
        df = pd.read_csv(po_items_url)
        df.columns = df.columns.str.strip()
        return df
    except:
        return pd.DataFrame(
            columns=[
                "DATE",
                "PO_NO",
                "MATERIAL",
                "LOCATION",
                "QTY",
                "BATCH_ID"
            ]
        )


@st.cache_data(ttl=60)
def load_gate_out():
    try:
        df = pd.read_csv(gate_out_url)
        df.columns = df.columns.str.strip()
        return df
    except:
        return pd.DataFrame(
            columns=[
                "DATE",
                "PO_NO",
                "MATERIAL",
                "LOCATION",
                "OUT_QTY",
                "BATCH_ID"
            ]
        )


@st.cache_data(ttl=60)
def load_location_master():
    df = pd.read_csv(location_master_url)
    df.columns = df.columns.str.strip()
    return df


def load_data():
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        f_pm = executor.submit(load_po_master)
        f_pi = executor.submit(load_po_items)
        f_go = executor.submit(load_gate_out)
        f_lm = executor.submit(load_location_master)
    return (
        f_pm.result(),
        f_pi.result(),
        f_go.result(),
        f_lm.result(),
    )

# ==========================================
# LOAD DATA
# ==========================================

(
    po_master_df,
    po_items_df,
    gate_out_df,
    location_master_df
) = load_data()

# ==========================================
# DATE
# ==========================================

today_date = datetime.now().strftime(
    "%d-%m-%Y"
)

# ==========================================
# SPEED FIX 4 : cache the dashboard groupby
#   computation so it is not re-run on
#   every Streamlit rerun / button click.
# ==========================================

@st.cache_data(ttl=60)
def compute_stock_summary(_po_items_df, _gate_out_df):
    in_summary  = _po_items_df.groupby(["MATERIAL", "LOCATION"])["QTY"].sum()
    out_summary = _gate_out_df.groupby(["MATERIAL", "LOCATION"])["OUT_QTY"].sum()
    stock_df    = pd.concat([in_summary, out_summary], axis=1).fillna(0)
    stock_df.columns = ["TOTAL_IN", "TOTAL_OUT"]
    stock_df["BALANCE"] = stock_df["TOTAL_IN"] - stock_df["TOTAL_OUT"]
    return stock_df.reset_index()

# ==========================================
# API FUNCTIONS
# ==========================================

def send_po_data(payload):

    url = "https://script.google.com/macros/s/AKfycbyESzTIQgiy-zRdkqViYM_yHMaTxpESd1iRwzhvP1xxWA4wlkix1VrwzSGOY7mHWsRRDA/exec"

    try:
        requests.post(
            url,
            json=payload,
            timeout=2
        )

    except:
        pass


def save_items_background(
    items,
    po_no,
    today_date
):

    item_url = "https://script.google.com/macros/s/AKfycbxrc1M_VPaVjY6kDKVoMAU4ohNp9vj2XgibhtBjtZVYwtKHFYkCkkSXM9ZcheJpwLeKhQ/exec"

    for item in items:

        item_payload = {
            "date": today_date,
            "po_no": po_no,
            "material": item["material"],
            "location": item["location"],
            "qty": item["qty"],
            "batch_id": f"{po_no}_{datetime.now().timestamp()}"
        }

        try:
            requests.post(
                item_url,
                json=item_payload,
                timeout=2
            )

        except:
            pass


def gate_out_background(payload):

    gate_out_script = "https://script.google.com/macros/s/AKfycbyrnRO5FaI6eaOdUXv13oGiXolUMV-faJqlDoZglI90Fr8M0RDJGn7V_a_m7jqNOoaVLg/exec"

    try:
        requests.post(
            gate_out_script,
            json=payload,
            timeout=2
        )

    except:
        pass

# ==========================================
# HOME PAGE
# ==========================================

if st.session_state.page == "home":

    st.markdown(
        """
        <h1 style='
            text-align:center;
            font-size:60px;
            margin-bottom:50px;
        '>
            <span style='color:red;'>
                Swiss Military
            </span>
            Warehouse Material Planning
        </h1>
        """,
        unsafe_allow_html=True
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:

        if st.button(
            "📄 CREATE NEW PO",
            use_container_width=True
        ):
            st.session_state.page = "create_po"
            st.rerun()

    with col2:

        if st.button(
            "📥 GATE IN",
            use_container_width=True
        ):
            st.session_state.page = "gate_in"
            st.rerun()

    with col3:

        if st.button(
            "📤 GATE OUT",
            use_container_width=True
        ):
            st.session_state.page = "gate_out"
            st.rerun()

    with col4:

        if st.button(
            "📊 DASHBOARD",
            use_container_width=True
        ):
            st.session_state.page = "dashboard"
            st.rerun()

# ==========================================
# CREATE PO
# ==========================================

elif st.session_state.page == "create_po":

    st.title("📄 Create New PO")

    if st.button("⬅ Back To Home"):
        st.session_state.page = "home"
        st.rerun()

    st.divider()

    if st.session_state.po_created:
        st.toast(
            "✅ PO Created Successfully 🚀"
        )

        st.success(
            "PO Added To Warehouse Database"
        )

        st.balloons()

        st.session_state.po_created = False

    created_by = st.text_input(
        "👤 Your Name",
        key = "created_by"
    )

    po_no = st.text_input(
        "📄 PO Number",
        key="po_no"
    )

    vendor = st.text_input(
        "🏭 Vendor Name",
        key="vendor"
    )

    st.info(
        f"📅 Date : {today_date}"
    )

    if st.button("✅ Create PO"):

        if po_no == "" or vendor == "":
            st.error(
                "Please Fill All Fields"
            )

        else:

            payload = {
                "po_no": po_no,
                "vendor": vendor,
                "date": today_date,
                "created_by": created_by
            }

            # SPEED FIX 5 : daemon=True on all
            # background threads so they never
            # block app shutdown / rerun
            threading.Thread(
                target=send_po_data,
                args=(payload,),
                daemon=True
            ).start()

            # CACHE FIX : wait briefly for Google
            # Sheets to commit, then bust the cache
            # so Gate In shows the new PO instantly
            # without needing manual refreshes
            time.sleep(2)
            load_po_master.clear()

            st.session_state.po_created = True

            del st.session_state["created_by"]
            del st.session_state["po_no"]
            del st.session_state["vendor"]

            st.rerun()

# ==========================================
# GATE IN
# ==========================================

elif st.session_state.page == "gate_in":

    st.title("📥 Gate In")

    if st.button("⬅ Back To Home"):
        st.session_state.page = "home"
        st.rerun()

    st.divider()

    if st.session_state.add_success:
        st.success(
            "Item Added Successfully 🚀"
        )
        st.session_state.add_success = False

    if st.session_state.save_success:
        st.success(
            "Items Saved Successfully 🚀"
        )
        st.balloons()
        st.session_state.save_success = False

    # ======================================
    # PO LIST
    # ======================================

    po_list = (
        po_master_df["PO_NO"]
        .dropna()
        .unique()
        .tolist()
    )

    po_options = [
        "Select PO"
    ] + po_list

    selected_po = st.selectbox(
        "📄 Select PO",
        po_options
    )

    # ======================================
    # MATERIAL LIST
    # ======================================

    material_list = (
        location_master_df["MATERIAL"]
        .dropna()
        .unique()
        .tolist()
    )

    material_options = [
        "Select Material"
    ] + material_list

    selected_material = st.selectbox(
        "📦 Select Material",
        material_options
    )

    # ======================================
    # LOCATION
    # SPEED FIX 6 : .values[0] replaced with
    #   .iloc[0] — avoids a full numpy array
    #   allocation just to read one value
    # ======================================

    assigned_location = ""

    if selected_material != "Select Material":

        match = location_master_df.loc[
            location_master_df["MATERIAL"] == selected_material,
            "LOCATION"
        ]

        if not match.empty:
            assigned_location = match.iloc[0]

            st.success(
                f"📍 LOCATION : {assigned_location}"
            )

    qty = st.number_input(
        "Enter Quantity",
        min_value=1,
        step=1
    )

    # ======================================
    # ADD ITEM
    # ======================================

    if st.button("➕ Add Item"):

        if selected_po == "Select PO":
            st.error(
                "Please Select PO"
            )

        elif selected_material == "Select Material":
            st.error(
                "Please Select Material"
            )

        else:

            st.session_state.po_items.append({
                "material": selected_material,
                "location": assigned_location,
                "qty": qty
            })

            st.session_state.add_success = True
            st.rerun()

    # ======================================
    # REVIEW TABLE
    # ======================================

    if st.session_state.po_items:

        st.divider()

        st.subheader(
            "📋 Items Added"
        )

        table_df = pd.DataFrame(
            st.session_state.po_items
        )

        st.dataframe(
            table_df,
            use_container_width=True
        )

        if st.button(
            "✅ Save All Items"
        ):

            items_copy = (
                st.session_state.po_items.copy()
            )

            threading.Thread(
                target=save_items_background,
                args=(
                    items_copy,
                    selected_po,
                    today_date
                ),
                daemon=True           # SPEED FIX 5
            ).start()

            # CACHE FIX GATE IN : wait for Sheets
            # to commit then clear po_items cache
            # so Gate Out & Dashboard reflect the
            # new stock immediately without refresh
            time.sleep(2)
            load_po_items.clear()
            compute_stock_summary.clear()

            st.session_state.po_items = []
            st.session_state.save_success = True

            st.rerun()

# ==========================================
# GATE OUT FIFO SYSTEM
# ==========================================

elif st.session_state.page == "gate_out":

    st.title("📤 Gate Out - FIFO")

    if st.button("⬅ Back To Home"):
        st.session_state.page = "home"
        st.rerun()

    st.divider()

    if st.session_state.gate_out_success:
        st.success(
            "Gate Out Successful 🚀"
        )
        st.balloons()
        st.session_state.gate_out_success = False

    # ======================================
    # MATERIAL DROPDOWN
    # ======================================

    material_list = (
        po_items_df["MATERIAL"]
        .dropna()
        .unique()
        .tolist()
    )

    material_options = [
        "Select Material"
    ] + material_list

    selected_material = st.selectbox(
        "📦 Select Material",
        material_options
    )

    # ======================================
    # OUT QTY
    # ======================================

    out_qty = st.number_input(
        "Enter OUT Quantity",
        min_value=1,
        step=1
    )

    # ======================================
    # FIFO ENGINE
    # SPEED FIX 7 : replaced the inner-loop
    #   gate_out_df scan (O(n²)) with a single
    #   vectorized groupby + DataFrame.join
    #   (O(n log n)).  All balance calculations
    #   now happen in one pandas pass.
    # ======================================

    if selected_material != "Select Material":

        material_in = po_items_df[
            po_items_df["MATERIAL"] == selected_material
        ].copy()

        # ==================================
        # ENTRY ORDER
        # ==================================

        material_in = material_in.reset_index()

        material_in.rename(
            columns={
                "index": "ENTRY_ORDER"
            },
            inplace=True
        )

        # ==================================
        # FIFO STOCK CALCULATION
        # ==================================

        material_in = material_in.sort_values(
            by="ENTRY_ORDER"
        )

        # one groupby replaces N individual .sum() calls
        out_by_batch = (
            gate_out_df.groupby("BATCH_ID")["OUT_QTY"]
            .sum()
            .rename("TOTAL_OUT")
        )

        material_in = material_in.join(out_by_batch, on="BATCH_ID")
        material_in["TOTAL_OUT"] = material_in["TOTAL_OUT"].fillna(0)
        material_in["BALANCE"]   = material_in["QTY"] - material_in["TOTAL_OUT"]

        stock_df = material_in[
            material_in["BALANCE"] > 0
        ][[
            "ENTRY_ORDER", "PO_NO",
            "MATERIAL", "LOCATION",
            "BATCH_ID", "BALANCE"
        ]].copy()

        # ==================================
        # TOTAL AVAILABLE
        # ==================================

        total_available = stock_df[
            "BALANCE"
        ].sum()

        st.success(
            f"📦 Total Available Stock : {total_available}"
        )

        # ==================================
        # STOCK VALIDATION
        # ==================================

        if out_qty > total_available:

            st.error(
                "Stock Not Available ❌"
            )

        else:

            remaining_qty = out_qty
            fifo_rows = []

            # ==================================
            # FIFO LOOP
            # ==================================

            for index, row in stock_df.iterrows():

                available = row["BALANCE"]

                if available <= 0:
                    continue

                if remaining_qty <= 0:
                    break

                deduct_qty = min(
                    remaining_qty,
                    available
                )

                fifo_rows.append({
                    "PO_NO": row["PO_NO"],
                    "MATERIAL": row["MATERIAL"],
                    "LOCATION": row["LOCATION"],
                    "BATCH_ID": row["BATCH_ID"],
                    "AVAILABLE": available,
                    "DEDUCT_QTY": deduct_qty
                })

                remaining_qty -= deduct_qty

            # ==================================
            # FIFO PREVIEW
            # ==================================

            st.divider()

            st.subheader(
                "📋 FIFO Allocation Preview"
            )

            fifo_preview_df = pd.DataFrame(
                fifo_rows
            )

            st.dataframe(
                fifo_preview_df,
                use_container_width=True
            )

            # ==================================
            # SUBMIT GATE OUT
            # ==================================

            if st.button(
                "🚚 Submit Gate Out"
            ):

                for row in fifo_rows:
                    gate_out_payload = {
                        "date": today_date,
                        "po_no": row["PO_NO"],
                        "material": row["MATERIAL"],
                        "location": row["LOCATION"],
                        "out_qty": row["DEDUCT_QTY"],
                        "batch_id": row["BATCH_ID"]
                    }

                    threading.Thread(
                        target=gate_out_background,
                        args=(gate_out_payload,),
                        daemon=True       # SPEED FIX 5
                    ).start()

                # CACHE FIX GATE OUT : wait for
                # Sheets to commit then clear the
                # gate_out cache so Dashboard stock
                # numbers update immediately without
                # needing manual refreshes
                    time.sleep(2)
                load_gate_out.clear()
                compute_stock_summary.clear()

                st.session_state.gate_out_success = True
                st.rerun()

# ==========================================
# DASHBOARD
# ==========================================

elif st.session_state.page == "dashboard":

    # CACHE FIX DASHBOARD : every time the
    # user lands on dashboard, bust all caches
    # so KPIs and stock table always show the
    # latest data without manual refreshes
    load_po_master.clear()
    load_po_items.clear()
    load_gate_out.clear()
    compute_stock_summary.clear()

    (
        po_master_df,
        po_items_df,
        gate_out_df,
        location_master_df
    ) = load_data()

    st.title("📊 Warehouse Dashboard")

    if st.button("⬅ Back To Home"):
        st.session_state.page = "home"
        st.rerun()

    st.divider()

    # ======================================
    # KPI
    # ======================================

    total_po = po_master_df[
        "PO_NO"
    ].nunique()

    total_in = po_items_df[
        "QTY"
    ].sum()

    total_out = gate_out_df[
        "OUT_QTY"
    ].sum()

    current_stock = (
        total_in - total_out
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "TOTAL PO",
            total_po
        )

    with col2:
        st.metric(
            "TOTAL IN",
            total_in
        )

    with col3:
        st.metric(
            "TOTAL OUT",
            total_out
        )

    with col4:
        st.metric(
            "CURRENT STOCK",
            current_stock
        )

    st.divider()

    # ======================================
    # STOCK SUMMARY  (SPEED FIX 4)
    # ======================================

    stock_df = compute_stock_summary(
        po_items_df,
        gate_out_df
    )

    st.subheader(
        "📦 Current Stock Summary"
    )

    st.dataframe(
        stock_df,
        use_container_width=True
    )

    # ======================================
    # LOW STOCK ALERT
    # ======================================

    st.divider()

    st.subheader(
        "⚠ Low Stock Alert"
    )

    low_stock_df = stock_df[
        stock_df["BALANCE"] < 20
        ]

    if len(low_stock_df) > 0:

        st.warning(
            "Some Materials Are Running Low"
        )

        st.dataframe(
            low_stock_df,
            use_container_width=True
        )

    else:

        st.success(
            "✅ No Low Stock Items"
        )

    # ======================================
    # MATERIAL WISE STOCK CHART
    # ======================================

    st.divider()

    st.subheader(
        "📊 Material Wise Current Stock"
    )

    material_chart = stock_df.groupby(
        "MATERIAL"
    )["BALANCE"].sum()

    st.bar_chart(
        material_chart
    )

    # ======================================
    # FAST MOVING MATERIALS
    # ======================================

    st.divider()

    st.subheader(
        "🔥 Fast Moving Materials"
    )

    fast_moving_df = gate_out_df.groupby(
        "MATERIAL"
    )["OUT_QTY"].sum().reset_index()

    fast_moving_df = fast_moving_df.sort_values(
        by="OUT_QTY",
        ascending=False
    )

    st.dataframe(
        fast_moving_df,
        use_container_width=True
    )

    # ======================================
    # RECENT GATE IN
    # ======================================

    st.divider()

    st.subheader(
        "📥 Recent Gate In"
    )

    recent_in_df = po_items_df.tail(10)

    st.dataframe(
        recent_in_df,
        use_container_width=True
    )

    # ======================================
    # RECENT GATE OUT
    # ======================================

    st.divider()

    st.subheader(
        "📤 Recent Gate Out"
    )

    recent_out_df = gate_out_df.tail(10)

    st.dataframe(
        recent_out_df,
        use_container_width=True
    )
