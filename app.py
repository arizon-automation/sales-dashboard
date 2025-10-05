import streamlit as st
import streamlit_authenticator as stauth
import requests
import hmac
import hashlib
import base64
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
import yaml
from yaml.loader import SafeLoader
import pickle
import os
from pathlib import Path

# Page config
st.set_page_config(
    page_title="Sales Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Persistent cache directory
CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)

def get_cache_file(cache_key):
    """Get cache file path for a given key"""
    return CACHE_DIR / f"{cache_key}.pkl"

def load_from_cache(cache_key, max_age_hours=2):
    """Load data from persistent cache if available and not expired"""
    cache_file = get_cache_file(cache_key)
    
    if cache_file.exists():
        # Check if cache is still valid
        file_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
        if file_age.total_seconds() < max_age_hours * 3600:
            try:
                with open(cache_file, 'rb') as f:
                    return pickle.load(f)
            except:
                pass
    return None

def save_to_cache(cache_key, data):
    """Save data to persistent cache"""
    cache_file = get_cache_file(cache_key)
    try:
        with open(cache_file, 'wb') as f:
            pickle.dump(data, f)
    except:
        pass

# Custom CSS
st.markdown("""
    <style>
    .main {
        padding: 0rem 1rem;
    }
    .stMetric {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
    }
    </style>
""", unsafe_allow_html=True)

# Load configuration from secrets
try:
    # Initialize authenticator with new API format
    authenticator = stauth.Authenticate(
        credentials=st.secrets['credentials'].to_dict(),
        cookie_name='sales_dashboard_auth',
        cookie_key='random_signature_key_123',
        cookie_expiry_days=30
    )
except Exception as e:
    st.error("⚠️ Configuration error. Please set up your secrets.toml file correctly.")
    st.error(f"Error details: {str(e)}")
    st.stop()

# Unleashed API Client
class UnleashedAPI:
    def __init__(self, api_id, api_key):
        self.api_id = api_id
        self.api_key = api_key
        self.base_url = "https://api.unleashedsoftware.com"
    
    def _generate_signature(self, query_string):
        """Generate HMAC signature for Unleashed API from query string"""
        message = query_string.encode('utf-8')
        signature = hmac.new(
            self.api_key.encode('utf-8'),
            message,
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode('utf-8')
    
    def _make_request(self, endpoint, params=None):
        """Make authenticated request to Unleashed API"""
        # Build query string for URL
        if params:
            from urllib.parse import urlencode
            query_string = urlencode(params)
        else:
            query_string = ""
            
        # Generate signature from QUERY STRING ONLY (not the full path)
        signature = self._generate_signature(query_string)
        
        headers = {
            'Accept': 'application/json',
            'api-auth-id': self.api_id,
            'api-auth-signature': signature
        }
        
        # Build full URL
        full_url = f"{self.base_url}{endpoint}"
        if query_string:
            full_url = f"{full_url}?{query_string}"
        
        response = requests.get(full_url, headers=headers)
        response.raise_for_status()
        return response.json()
    
    def get_all_pages(self, endpoint, params=None):
        """Fetch all pages of data"""
        all_items = []
        page = 1
        
        while True:
            current_params = params.copy() if params else {}
            current_params['page'] = page
            
            data = self._make_request(endpoint, current_params)
            items = data.get('Items', [])
            
            if not items:
                break
            
            all_items.extend(items)
            
            pagination = data.get('Pagination', {})
            if page >= pagination.get('NumberOfPages', 1):
                break
            
            page += 1
        
        return all_items
    
    def get_sales_orders(self, start_date, end_date):
        """Get completed sales orders for date range with persistent caching"""
        cache_key = f"sales_orders_{start_date}_{end_date}"
        
        # Try to load from persistent cache first
        cached_data = load_from_cache(cache_key)
        if cached_data is not None:
            return cached_data
        
        # Fetch from API if not in cache
        params = {
            'completedAfter': start_date,
            'completedBefore': end_date,
            'orderStatus': 'Completed'
        }
        data = self.get_all_pages('/SalesOrders', params)
        
        # Save to persistent cache
        save_to_cache(cache_key, data)
        return data
    
    def get_products(self):
        """Get all products with persistent caching"""
        cache_key = "products_all"
        
        # Try to load from persistent cache first
        cached_data = load_from_cache(cache_key)
        if cached_data is not None:
            return cached_data
        
        # Fetch from API if not in cache
        data = self.get_all_pages('/Products')
        
        # Save to persistent cache
        save_to_cache(cache_key, data)
        return data
    
    def get_salespersons(self):
        """Get all salespersons with persistent caching"""
        cache_key = "salespersons_all"
        
        # Try to load from persistent cache first
        cached_data = load_from_cache(cache_key)
        if cached_data is not None:
            return cached_data
        
        # Fetch from API if not in cache
        data = self.get_all_pages('/SalesPersons')
        
        # Save to persistent cache
        save_to_cache(cache_key, data)
        return data
    
    def get_credit_notes(self, start_date, end_date):
        """Get credit notes for date range with persistent caching"""
        cache_key = f"credit_notes_{start_date}_{end_date}"
        
        # Try to load from persistent cache first
        cached_data = load_from_cache(cache_key)
        if cached_data is not None:
            return cached_data
        
        # Fetch from API if not in cache
        params = {
            'startDate': start_date,
            'endDate': end_date
        }
        data = self.get_all_pages('/CreditNotes', params)
        
        # Save to persistent cache
        save_to_cache(cache_key, data)
        return data


# Analytics Functions
def calculate_total_sales(orders):
    """Calculate total sales from orders (GST exclusive)"""
    return sum(order.get('SubTotal', 0) for order in orders)

def calculate_total_credit_notes(credit_notes):
    """Calculate total credit notes amount (GST exclusive)"""
    return sum(note.get('SubTotal', 0) for note in credit_notes)

def get_top_customers_comparison(current_orders, previous_orders, limit=10):
    """Get top customers by revenue with comparison (GST exclusive)"""
    def get_customer_revenue(orders):
        customer_data = {}
        for order in orders:
            customer = order.get('Customer', {})
            customer_code = customer.get('CustomerCode', 'Unknown')
            customer_name = customer.get('CustomerName', 'Unknown')
            subtotal = order.get('SubTotal', 0)
            
            if customer_code not in customer_data:
                customer_data[customer_code] = {'name': customer_name, 'revenue': 0}
            
            customer_data[customer_code]['revenue'] += subtotal
        return customer_data
    
    current_data = get_customer_revenue(current_orders)
    previous_data = get_customer_revenue(previous_orders)
    
    # Merge current and previous
    all_customers = set(current_data.keys()) | set(previous_data.keys())
    
    comparison = []
    for customer_code in all_customers:
        current = current_data.get(customer_code, {'name': 'Unknown', 'revenue': 0})
        previous = previous_data.get(customer_code, {'name': 'Unknown', 'revenue': 0})
        
        current_rev = current['revenue']
        previous_rev = previous['revenue']
        change = current_rev - previous_rev
        change_pct = (change / previous_rev * 100) if previous_rev > 0 else (100 if current_rev > 0 else 0)
        
        comparison.append({
            'Customer': current['name'] if current['name'] != 'Unknown' else previous['name'],
            'Current Revenue': current_rev,
            'Previous Revenue': previous_rev,
            'Change': change,
            'Change %': change_pct
        })
    
    df = pd.DataFrame(comparison)
    return df.nlargest(limit, 'Current Revenue')

def get_top_products_comparison(current_orders, previous_orders, limit=10):
    """Get top products by revenue with comparison (GST exclusive)"""
    def get_product_revenue(orders):
        product_data = {}
        for order in orders:
            for line in order.get('SalesOrderLines', []):
                product = line.get('Product', {})
                product_code = product.get('ProductCode', 'Unknown')
                product_name = product.get('ProductDescription', 'Unknown')
                line_total = line.get('LineTotal', 0)
                
                if product_code not in product_data:
                    product_data[product_code] = {'name': product_name, 'revenue': 0}
                
                product_data[product_code]['revenue'] += line_total
        return product_data
    
    current_data = get_product_revenue(current_orders)
    previous_data = get_product_revenue(previous_orders)
    
    # Merge current and previous
    all_products = set(current_data.keys()) | set(previous_data.keys())
    
    comparison = []
    for product_code in all_products:
        current = current_data.get(product_code, {'name': 'Unknown', 'revenue': 0})
        previous = previous_data.get(product_code, {'name': 'Unknown', 'revenue': 0})
        
        current_rev = current['revenue']
        previous_rev = previous['revenue']
        change = current_rev - previous_rev
        change_pct = (change / previous_rev * 100) if previous_rev > 0 else (100 if current_rev > 0 else 0)
        
        comparison.append({
            'Product': current['name'] if current['name'] != 'Unknown' else previous['name'],
            'Current Revenue': current_rev,
            'Previous Revenue': previous_rev,
            'Change': change,
            'Change %': change_pct
        })
    
    df = pd.DataFrame(comparison)
    return df.nlargest(limit, 'Current Revenue')

def get_top_products_by_margin_comparison(current_orders, previous_orders, products_list, limit=10):
    """Get top products by margin with comparison (GST exclusive)"""
    product_costs = {p['ProductCode']: p.get('DefaultPurchasePrice', 0) for p in products_list}
    
    def get_product_margin(orders):
        product_data = {}
        for order in orders:
            for line in order.get('SalesOrderLines', []):
                product = line.get('Product', {})
                product_code = product.get('ProductCode', 'Unknown')
                product_name = product.get('ProductDescription', 'Unknown')
                
                line_total = line.get('LineTotal', 0)
                quantity = line.get('OrderQuantity', 0)
                
                unit_cost = line.get('UnitCost', 0)
                if unit_cost == 0:
                    product_obj = line.get('Product', {})
                    unit_cost = (
                        product_obj.get('DefaultPurchasePrice', 0) or 
                        product_obj.get('AverageLandPrice', 0) or
                        product_costs.get(product_code, 0)
                    )
                
                total_cost = quantity * unit_cost
                margin = line_total - total_cost
                
                if product_code not in product_data:
                    product_data[product_code] = {'name': product_name, 'margin': 0, 'revenue': 0}
                
                product_data[product_code]['margin'] += margin
                product_data[product_code]['revenue'] += line_total
        return product_data
    
    current_data = get_product_margin(current_orders)
    previous_data = get_product_margin(previous_orders)
    
    # Merge current and previous
    all_products = set(current_data.keys()) | set(previous_data.keys())
    
    comparison = []
    for product_code in all_products:
        current = current_data.get(product_code, {'name': 'Unknown', 'margin': 0, 'revenue': 0})
        previous = previous_data.get(product_code, {'name': 'Unknown', 'margin': 0, 'revenue': 0})
        
        current_margin = current['margin']
        previous_margin = previous['margin']
        current_rev = current['revenue']
        
        change = current_margin - previous_margin
        change_pct = (change / previous_margin * 100) if previous_margin > 0 else (100 if current_margin > 0 else 0)
        margin_pct = (current_margin / current_rev * 100) if current_rev > 0 else 0
        
        comparison.append({
            'Product': current['name'] if current['name'] != 'Unknown' else previous['name'],
            'Current Margin': current_margin,
            'Previous Margin': previous_margin,
            'Margin %': margin_pct,
            'Change': change,
            'Change %': change_pct
        })
    
    df = pd.DataFrame(comparison)
    return df.nlargest(limit, 'Current Margin')

def get_salesperson_revenue(orders):
    """Get revenue per salesperson (GST exclusive)"""
    salesperson_data = {}
    
    for order in orders:
        salesperson = order.get('SalesPerson', {})
        if not salesperson:
            continue
            
        sp_code = salesperson.get('Guid', 'Unknown')
        sp_name = salesperson.get('FullName', 'Unknown')
        subtotal = order.get('SubTotal', 0)
        
        if sp_code not in salesperson_data:
            salesperson_data[sp_code] = {
                'name': sp_name,
                'revenue': 0,
                'orders': 0
            }
        
        salesperson_data[sp_code]['revenue'] += subtotal
        salesperson_data[sp_code]['orders'] += 1
    
    df = pd.DataFrame([
        {
            'Salesperson': data['name'],
            'Revenue': data['revenue'],
            'Orders': data['orders']
        }
        for data in salesperson_data.values()
    ])
    
    if len(df) > 0:
        return df.sort_values('Revenue', ascending=False)
    return df

def compare_customer_growth(current_orders, previous_orders, limit=10):
    """Compare customer revenue growth (GST exclusive)"""
    def get_customer_revenue(orders):
        revenue = {}
        for order in orders:
            customer = order.get('Customer', {})
            customer_code = customer.get('CustomerCode', 'Unknown')
            customer_name = customer.get('CustomerName', 'Unknown')
            subtotal = order.get('SubTotal', 0)
            
            if customer_code not in revenue:
                revenue[customer_code] = {'name': customer_name, 'revenue': 0}
            revenue[customer_code]['revenue'] += subtotal
        return revenue
    
    current_rev = get_customer_revenue(current_orders)
    previous_rev = get_customer_revenue(previous_orders)
    
    all_customers = set(current_rev.keys()) | set(previous_rev.keys())
    
    comparison = []
    for customer_code in all_customers:
        current = current_rev.get(customer_code, {'name': 'Unknown', 'revenue': 0})
        previous = previous_rev.get(customer_code, {'name': 'Unknown', 'revenue': 0})
        
        change = current['revenue'] - previous['revenue']
        percent_change = (change / previous['revenue'] * 100) if previous['revenue'] > 0 else (100 if current['revenue'] > 0 else 0)
        
        comparison.append({
            'Customer': current['name'] if current['name'] != 'Unknown' else previous['name'],
            'Current Revenue': current['revenue'],
            'Previous Revenue': previous['revenue'],
            'Change': change,
            'Change %': percent_change
        })
    
    df = pd.DataFrame(comparison)
    growth = df.nlargest(limit, 'Change')
    decline = df.nsmallest(limit, 'Change')
    
    return growth, decline


# Main App
def main():
    # Authentication
    try:
        authenticator.login(location='sidebar')
        name = st.session_state.get('name')
        authentication_status = st.session_state.get('authentication_status')
        username = st.session_state.get('username')
    except Exception as e:
        st.error(f"Authentication error: {str(e)}")
        return
    
    if authentication_status == False:
        st.sidebar.error('Username/password is incorrect')
        st.title("📊 Sales Dashboard")
        st.info("Please login using the sidebar to access the dashboard.")
        return
    
    if authentication_status == None:
        st.sidebar.warning('Please enter your username and password')
        st.title("📊 Sales Dashboard")
        st.info("Please login using the sidebar to access the dashboard.")
        return
    
    # User is authenticated
    st.sidebar.success(f'Welcome *{name}*')
    authenticator.logout(location='sidebar')
    
    st.sidebar.divider()
    
    # Load Unleashed API credentials from secrets
    try:
        api_id = st.secrets['unleashed']['api_id']
        api_key = st.secrets['unleashed']['api_key']
    except Exception as e:
        st.error("⚠️ Unleashed API credentials not configured. Please contact your administrator.")
        return
    
    # Sidebar - Period Selection
    with st.sidebar:
        st.divider()
        st.header("📅 Period Selection")
        period = st.radio("Select Period", ["Monthly", "Quarterly"])
        
        if st.button("🔄 Refresh Data", width='stretch'):
            # Clear both in-memory and persistent cache
            st.cache_data.clear()
            # Clear all cache files
            for cache_file in CACHE_DIR.glob("*.pkl"):
                try:
                    cache_file.unlink()
                except:
                    pass
            st.rerun()
    
    # Initialize API client
    api = UnleashedAPI(api_id, api_key)
    
    # Calculate date ranges
    today = datetime.now()
    
    if period == "Monthly":
        current_start = today.replace(day=1).strftime('%Y-%m-%d')
        current_end = today.strftime('%Y-%m-%d')
        
        previous_month = today.replace(day=1) - timedelta(days=1)
        previous_start = previous_month.replace(day=1).strftime('%Y-%m-%d')
        # Match the same day of the month for previous period
        try:
            previous_end = previous_month.replace(day=today.day).strftime('%Y-%m-%d')
        except ValueError:
            # If previous month doesn't have this day, use last day of that month
            previous_end = previous_month.strftime('%Y-%m-%d')
        
        period_name = "Month"
    else:
        # Calculate current quarter (Q1=0, Q2=1, Q3=2, Q4=3)
        quarter = (today.month - 1) // 3
        # Quarter start months: Q1=1, Q2=4, Q3=7, Q4=10
        quarter_start_month = quarter * 3 + 1
        current_start = datetime(today.year, quarter_start_month, 1).strftime('%Y-%m-%d')
        current_end = today.strftime('%Y-%m-%d')
        
        # Calculate how many days into the quarter we are
        quarter_start_date = datetime(today.year, quarter_start_month, 1)
        days_into_quarter = (today - quarter_start_date).days
        
        # Previous quarter
        if quarter == 0:
            prev_year = today.year - 1
            prev_quarter = 3  # Q4
        else:
            prev_year = today.year
            prev_quarter = quarter - 1
        
        # Previous quarter start
        prev_quarter_start_month = prev_quarter * 3 + 1
        previous_start = datetime(prev_year, prev_quarter_start_month, 1).strftime('%Y-%m-%d')
        
        # Previous quarter end: same number of days into that quarter as we are now
        prev_quarter_start_date = datetime(prev_year, prev_quarter_start_month, 1)
        previous_end_date = prev_quarter_start_date + timedelta(days=days_into_quarter)
        previous_end = previous_end_date.strftime('%Y-%m-%d')
        
        period_name = "Quarter"
    
    # Store fetch time in session state
    if 'last_fetch_time' not in st.session_state:
        st.session_state.last_fetch_time = datetime.now()
    
    # Excluded customers
    EXCLUDED_CUSTOMERS = ['Virtugroup', 'Fengrong']
    
    # Fetch data with loading spinner
    try:
        with st.spinner("📥 Loading data..."):
            fetch_start = datetime.now()
            all_current_orders = api.get_sales_orders(current_start, current_end)
            all_previous_orders = api.get_sales_orders(previous_start, previous_end)
            products = api.get_products()
            all_current_credit_notes = api.get_credit_notes(current_start, current_end)
            all_previous_credit_notes = api.get_credit_notes(previous_start, previous_end)
            
            # Filter out excluded customers
            current_orders = [
                order for order in all_current_orders 
                if order.get('Customer', {}).get('CustomerCode') not in EXCLUDED_CUSTOMERS
            ]
            previous_orders = [
                order for order in all_previous_orders 
                if order.get('Customer', {}).get('CustomerCode') not in EXCLUDED_CUSTOMERS
            ]
            current_credit_notes = [
                note for note in all_current_credit_notes 
                if note.get('Customer', {}).get('CustomerCode') not in EXCLUDED_CUSTOMERS
            ]
            previous_credit_notes = [
                note for note in all_previous_credit_notes 
                if note.get('Customer', {}).get('CustomerCode') not in EXCLUDED_CUSTOMERS
            ]
            
            fetch_duration = (datetime.now() - fetch_start).total_seconds()
            
            # Update fetch time only if it took more than 0.5 seconds (indicating actual API call)
            if fetch_duration > 0.5:
                st.session_state.last_fetch_time = datetime.now()
        
        # Show data status with fetch time info
        time_since_fetch = datetime.now() - st.session_state.last_fetch_time
        minutes_ago = int(time_since_fetch.total_seconds() / 60)
        
        if minutes_ago == 0:
            time_str = "just now"
        elif minutes_ago < 60:
            time_str = f"{minutes_ago} minute{'s' if minutes_ago != 1 else ''} ago"
        else:
            hours_ago = minutes_ago // 60
            time_str = f"{hours_ago} hour{'s' if hours_ago != 1 else ''} ago"
        
        st.success(f"✅ Data ready! ({len(current_orders)} orders, {len(current_credit_notes)} credit notes) | Last updated: {time_str}")
        
    except Exception as e:
        st.error(f"❌ Error fetching data: {str(e)}")
        st.info("Please contact your administrator if this issue persists.")
        return
    
    # Calculate metrics
    current_sales = calculate_total_sales(current_orders)
    previous_sales = calculate_total_sales(previous_orders)
    sales_change = current_sales - previous_sales
    sales_change_percent = (sales_change / previous_sales * 100) if previous_sales > 0 else 0
    
    current_credit_total = calculate_total_credit_notes(current_credit_notes)
    previous_credit_total = calculate_total_credit_notes(previous_credit_notes)
    credit_change = current_credit_total - previous_credit_total
    credit_change_percent = (credit_change / previous_credit_total * 100) if previous_credit_total > 0 else 0
    
    # ============= DASHBOARD =============
    st.title("📊 Sales Dashboard")
    st.info("💡 **Note:** All amounts displayed are GST-exclusive (ex GST)")
    
    # Show date ranges being compared
    st.caption(f"**Current Period:** {current_start} to {current_end} | **Previous Period:** {previous_start} to {previous_end}")
    
    # Summary Cards
    if period == 'Monthly':
        st.header(f"📈 Summary - Month to Date")
    else:
        st.header(f"📈 Summary - Quarter to Date")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "Total Sales",
            f"${current_sales:,.2f}",
            f"{sales_change_percent:+.1f}% vs last {period_name.lower()}"
        )
    
    with col2:
        st.metric(
            "Orders Completed",
            len(current_orders),
            f"{len(current_orders) - len(previous_orders):+d}"
        )
    
    with col3:
        st.metric(
            "Credit Notes Issued",
            f"${current_credit_total:,.2f}",
            f"{credit_change_percent:+.1f}% vs last {period_name.lower()}"
        )
    
    col4, col5 = st.columns(2)
    
    with col4:
        st.metric(
            "Average Order Value",
            f"${current_sales / len(current_orders):,.2f}" if current_orders else "$0",
            ""
        )
    
    with col5:
        st.metric(
            "Revenue Change",
            f"${abs(sales_change):,.2f}",
            f"{sales_change_percent:+.1f}% - {'Increase' if sales_change >= 0 else 'Decrease'}"
        )
    
    st.divider()
    
    # Top Customers - Make expandable for cleaner view
    with st.expander("👥 Top 10 Customers by Revenue", expanded=True):
        top_customers = get_top_customers_comparison(current_orders, previous_orders)
        st.dataframe(
            top_customers.style.format({
                'Current Revenue': '${:,.2f}',
                'Previous Revenue': '${:,.2f}',
                'Change': '${:,.2f}',
                'Change %': '{:+.1f}%'
            }),
            width='stretch',
            hide_index=True,
            height=400
        )
    
        # Customer chart
        chart_title = 'Top 10 Customers - Revenue Comparison'
        fig = go.Figure(data=[
            go.Bar(name='Current Period', x=top_customers['Customer'], y=top_customers['Current Revenue'], marker_color='#3b82f6'),
            go.Bar(name='Previous Period', x=top_customers['Customer'], y=top_customers['Previous Revenue'], marker_color='#93c5fd')
        ])
        fig.update_layout(
            title=chart_title,
            barmode='group',
            xaxis_tickangle=-45
        )
        st.plotly_chart(fig, width='stretch')
    
    # Customer Growth Analysis
    with st.expander("📊 Customer Revenue Growth Analysis", expanded=True):
        
        growth, decline = compare_customer_growth(current_orders, previous_orders)
        
        st.subheader("📈 Top 10 Growing Customers")
        st.dataframe(
            growth.style.format({
                'Current Revenue': '${:,.2f}',
                'Previous Revenue': '${:,.2f}',
                'Change': '${:,.2f}',
                'Change %': '{:+.1f}%'
            }),
            width='stretch',
            hide_index=True,
            height=400
        )
        
        st.divider()
        
        st.subheader("📉 Top 10 Declining Customers")
        st.dataframe(
            decline.style.format({
                'Current Revenue': '${:,.2f}',
                'Previous Revenue': '${:,.2f}',
                'Change': '${:,.2f}',
                'Change %': '{:+.1f}%'
            }),
            width='stretch',
            hide_index=True,
            height=400
        )
    
    # Salesperson Performance
    with st.expander("👤 Salesperson Performance", expanded=True):
        
        current_sp_revenue = get_salesperson_revenue(current_orders)
        previous_sp_revenue = get_salesperson_revenue(previous_orders)
        
        if len(current_sp_revenue) > 0 and len(previous_sp_revenue) > 0:
            # Merge current and previous data
            sp_comparison = current_sp_revenue.merge(
                previous_sp_revenue, 
                on='Salesperson', 
                how='outer', 
                suffixes=('_current', '_previous')
            ).fillna(0)
            
            sp_comparison['Revenue Change'] = sp_comparison['Revenue_current'] - sp_comparison['Revenue_previous']
            sp_comparison['Change %'] = sp_comparison.apply(
                lambda row: ((row['Revenue_current'] - row['Revenue_previous']) / row['Revenue_previous'] * 100) 
                if row['Revenue_previous'] > 0 else (100 if row['Revenue_current'] > 0 else 0), 
                axis=1
            )
            sp_comparison = sp_comparison.sort_values('Revenue_current', ascending=False)
            
            # Display comparison table
            display_df = sp_comparison[['Salesperson', 'Revenue_current', 'Revenue_previous', 'Revenue Change', 'Change %']].copy()
            display_df.columns = ['Salesperson', 'Current Revenue', 'Previous Revenue', 'Change', 'Change %']
            st.dataframe(
                display_df.style.format({
                    'Current Revenue': '${:,.2f}',
                    'Previous Revenue': '${:,.2f}',
                    'Change': '${:,.2f}',
                    'Change %': '{:+.1f}%'
                }),
                width='stretch',
                hide_index=True,
                height=400
            )
            
            # Salesperson comparison chart
            chart_title = 'Salesperson Revenue Comparison'
            fig = go.Figure(data=[
                go.Bar(name='Current Period', x=sp_comparison['Salesperson'], y=sp_comparison['Revenue_current'], marker_color='#667eea'),
                go.Bar(name='Previous Period', x=sp_comparison['Salesperson'], y=sp_comparison['Revenue_previous'], marker_color='#764ba2')
            ])
            fig.update_layout(
                title=chart_title,
                barmode='group',
                xaxis_tickangle=-45
            )
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("No salesperson data available for the selected period.")
    
    # Top Products by Revenue
    with st.expander("📦 Top 10 Products by Revenue", expanded=True):
        top_products = get_top_products_comparison(current_orders, previous_orders)
        st.dataframe(
            top_products.style.format({
                'Current Revenue': '${:,.2f}',
                'Previous Revenue': '${:,.2f}',
                'Change': '${:,.2f}',
                'Change %': '{:+.1f}%'
            }),
            width='stretch',
            hide_index=True,
            height=400
        )
        
        # Product chart
        chart_title = 'Top 10 Products - Revenue Comparison'
        fig = go.Figure(data=[
            go.Bar(name='Current Period', x=top_products['Product'], y=top_products['Current Revenue'], marker_color='#10b981'),
            go.Bar(name='Previous Period', x=top_products['Product'], y=top_products['Previous Revenue'], marker_color='#86efac')
        ])
        fig.update_layout(
            title=chart_title,
            barmode='group',
            xaxis_tickangle=-45
        )
        st.plotly_chart(fig, width='stretch')
    
    # Footer
    st.divider()
    st.caption("💡 **Tip:** Data is cached for 2 hours. Use the '🔄 Refresh Data' button in the sidebar to force a refresh.")


if __name__ == "__main__":
    main()
