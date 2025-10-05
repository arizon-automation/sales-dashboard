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

# Page config
st.set_page_config(
    page_title="Sales Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
    config = {
        'credentials': st.secrets['credentials'].to_dict(),
        'cookie': {
            'name': 'sales_dashboard_auth',
            'key': 'random_signature_key_123',
            'expiry_days': 30
        }
    }
except Exception as e:
    st.error("⚠️ Configuration error. Please set up your secrets.toml file correctly.")
    st.stop()

# Initialize authenticator
authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

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
    
    @st.cache_data(ttl=7200)  # Cache for 2 hours
    def get_sales_orders(_self, start_date, end_date):
        """Get completed sales orders for date range"""
        params = {
            'completedAfter': start_date,
            'completedBefore': end_date,
            'orderStatus': 'Completed'
        }
        return _self.get_all_pages('/SalesOrders', params)
    
    @st.cache_data(ttl=7200)
    def get_products(_self):
        """Get all products"""
        return _self.get_all_pages('/Products')
    
    @st.cache_data(ttl=7200)
    def get_salespersons(_self):
        """Get all salespersons"""
        return _self.get_all_pages('/SalesPersons')


# Analytics Functions
def calculate_total_sales(orders):
    """Calculate total sales from orders"""
    return sum(order.get('Total', 0) for order in orders)

def get_top_customers(orders, limit=10):
    """Get top customers by revenue"""
    customer_data = {}
    
    for order in orders:
        customer = order.get('Customer', {})
        customer_code = customer.get('CustomerCode', 'Unknown')
        customer_name = customer.get('CustomerName', 'Unknown')
        total = order.get('Total', 0)
        
        if customer_code not in customer_data:
            customer_data[customer_code] = {
                'name': customer_name,
                'revenue': 0,
                'orders': 0
            }
        
        customer_data[customer_code]['revenue'] += total
        customer_data[customer_code]['orders'] += 1
    
    df = pd.DataFrame([
        {
            'Customer': data['name'],
            'Revenue': data['revenue'],
            'Orders': data['orders']
        }
        for data in customer_data.values()
    ])
    
    return df.nlargest(limit, 'Revenue')

def get_top_products(orders, limit=10):
    """Get top products by revenue"""
    product_data = {}
    
    for order in orders:
        for line in order.get('SalesOrderLines', []):
            product = line.get('Product', {})
            product_code = product.get('ProductCode', 'Unknown')
            product_name = product.get('ProductDescription', 'Unknown')
            line_total = line.get('LineTotal', 0)
            quantity = line.get('OrderQuantity', 0)
            
            if product_code not in product_data:
                product_data[product_code] = {
                    'name': product_name,
                    'revenue': 0,
                    'quantity': 0
                }
            
            product_data[product_code]['revenue'] += line_total
            product_data[product_code]['quantity'] += quantity
    
    df = pd.DataFrame([
        {
            'Product': data['name'],
            'Revenue': data['revenue'],
            'Quantity': data['quantity']
        }
        for data in product_data.values()
    ])
    
    return df.nlargest(limit, 'Revenue')

def get_top_products_by_margin(orders, products_list, limit=10):
    """Get top products by margin"""
    # Create product cost map
    product_costs = {p['ProductCode']: p.get('DefaultPurchasePrice', 0) for p in products_list}
    
    product_data = {}
    
    for order in orders:
        for line in order.get('SalesOrderLines', []):
            product = line.get('Product', {})
            product_code = product.get('ProductCode', 'Unknown')
            product_name = product.get('ProductDescription', 'Unknown')
            line_total = line.get('LineTotal', 0)
            quantity = line.get('OrderQuantity', 0)
            
            cost = product_costs.get(product_code, 0)
            margin = line_total - (quantity * cost)
            
            if product_code not in product_data:
                product_data[product_code] = {
                    'name': product_name,
                    'margin': 0,
                    'revenue': 0
                }
            
            product_data[product_code]['margin'] += margin
            product_data[product_code]['revenue'] += line_total
    
    df = pd.DataFrame([
        {
            'Product': data['name'],
            'Total Margin': data['margin'],
            'Revenue': data['revenue']
        }
        for data in product_data.values()
    ])
    
    return df.nlargest(limit, 'Total Margin')

def get_salesperson_revenue(orders):
    """Get revenue per salesperson"""
    salesperson_data = {}
    
    for order in orders:
        salesperson = order.get('SalesPerson', {})
        if not salesperson:
            continue
            
        sp_code = salesperson.get('Guid', 'Unknown')
        sp_name = salesperson.get('FullName', 'Unknown')
        total = order.get('Total', 0)
        
        if sp_code not in salesperson_data:
            salesperson_data[sp_code] = {
                'name': sp_name,
                'revenue': 0,
                'orders': 0
            }
        
        salesperson_data[sp_code]['revenue'] += total
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
    """Compare customer revenue growth"""
    def get_customer_revenue(orders):
        revenue = {}
        for order in orders:
            customer = order.get('Customer', {})
            customer_code = customer.get('CustomerCode', 'Unknown')
            customer_name = customer.get('CustomerName', 'Unknown')
            total = order.get('Total', 0)
            
            if customer_code not in revenue:
                revenue[customer_code] = {'name': customer_name, 'revenue': 0}
            revenue[customer_code]['revenue'] += total
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
    
    # Page selection
    st.sidebar.header("📑 Navigation")
    page = st.sidebar.radio(
        "Select Page",
        ["📊 Overview", "👥 Customers", "📦 Products", "👤 Salesperson"]
    )
    
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
        
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
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
        previous_end = previous_month.replace(day=today.day).strftime('%Y-%m-%d')
        
        period_name = "Month"
    else:
        quarter = (today.month - 1) // 3
        current_start = datetime(today.year, quarter * 3 + 1, 1).strftime('%Y-%m-%d')
        current_end = today.strftime('%Y-%m-%d')
        
        if quarter == 0:
            prev_year = today.year - 1
            prev_quarter = 3
        else:
            prev_year = today.year
            prev_quarter = quarter - 1
        
        previous_start = datetime(prev_year, prev_quarter * 3 + 1, 1).strftime('%Y-%m-%d')
        previous_end = datetime(prev_year, (prev_quarter + 1) * 3, 1).strftime('%Y-%m-%d')
        
        period_name = "Quarter"
    
    # Fetch data with loading spinner
    try:
        with st.spinner("📥 Fetching data from Unleashed..."):
            current_orders = api.get_sales_orders(current_start, current_end)
            previous_orders = api.get_sales_orders(previous_start, previous_end)
            products = api.get_products()
        
        st.success(f"✅ Data loaded successfully! ({len(current_orders)} orders in current period)")
        
    except Exception as e:
        st.error(f"❌ Error fetching data: {str(e)}")
        st.info("Please contact your administrator if this issue persists.")
        return
    
    # Calculate metrics
    current_sales = calculate_total_sales(current_orders)
    previous_sales = calculate_total_sales(previous_orders)
    sales_change = current_sales - previous_sales
    sales_change_percent = (sales_change / previous_sales * 100) if previous_sales > 0 else 0
    
    # ============= OVERVIEW PAGE =============
    if page == "📊 Overview":
        st.title("📊 Sales Dashboard - Overview")
        
        # Summary Cards
        if period == 'Monthly':
            st.header(f"📈 Summary - Month to Date")
        else:
            st.header(f"📈 Summary - Quarter to Date")
        
        col1, col2, col3, col4 = st.columns(4)
    
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
            "Average Order Value",
            f"${current_sales / len(current_orders):,.2f}" if current_orders else "$0",
            ""
        )
    
    with col4:
        st.metric(
            "Revenue Change",
            f"${abs(sales_change):,.2f}",
            f"{sales_change_percent:+.1f}% - {'Increase' if sales_change >= 0 else 'Decrease'}"
        )
    
    st.divider()
    
    # Top Customers
    st.header("👥 Top 10 Customers by Revenue")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if period == 'Monthly':
            st.subheader("Month to Date")
        else:
            st.subheader("Quarter to Date")
        current_top_customers = get_top_customers(current_orders)
        st.dataframe(
            current_top_customers.style.format({'Revenue': '${:,.2f}'}),
            use_container_width=True,
            hide_index=True
        )
    
    with col2:
        if period == 'Monthly':
            st.subheader("Last Month Same Period")
        else:
            st.subheader("Last Quarter Same Period")
        previous_top_customers = get_top_customers(previous_orders)
        st.dataframe(
            previous_top_customers.style.format({'Revenue': '${:,.2f}'}),
            use_container_width=True,
            hide_index=True
        )
    
    # Customer chart
    chart_title = 'Top 10 Customers - Month to Date' if period == 'Monthly' else 'Top 10 Customers - Quarter to Date'
    fig = px.bar(
        current_top_customers,
        x='Customer',
        y='Revenue',
        title=chart_title,
        color='Revenue',
        color_continuous_scale='Blues'
    )
    fig.update_layout(showlegend=False, xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)
    
    st.divider()
    
    # Customer Growth Analysis
    st.header("📊 Customer Revenue Growth Analysis")
    
    growth, decline = compare_customer_growth(current_orders, previous_orders)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Top 10 Growing Customers")
        st.dataframe(
            growth.style.format({
                'Current Revenue': '${:,.2f}',
                'Previous Revenue': '${:,.2f}',
                'Change': '${:,.2f}',
                'Change %': '{:+.1f}%'
            }),
            use_container_width=True,
            hide_index=True
        )
    
    with col2:
        st.subheader("📉 Top 10 Declining Customers")
        st.dataframe(
            decline.style.format({
                'Current Revenue': '${:,.2f}',
                'Previous Revenue': '${:,.2f}',
                'Change': '${:,.2f}',
                'Change %': '{:+.1f}%'
            }),
            use_container_width=True,
            hide_index=True
        )
    
    st.divider()
    
    # Salesperson Performance
    st.header("👤 Salesperson Performance")
    
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
        
        col1, col2 = st.columns(2)
        
        with col1:
            if period == 'Monthly':
                st.subheader("Month to Date")
            else:
                st.subheader("Quarter to Date")
            
            display_df = sp_comparison[['Salesperson', 'Revenue_current', 'Orders_current']].copy()
            display_df.columns = ['Salesperson', 'Revenue', 'Orders']
            st.dataframe(
                display_df.style.format({'Revenue': '${:,.2f}', 'Orders': '{:.0f}'}),
                use_container_width=True,
                hide_index=True
            )
        
        with col2:
            if period == 'Monthly':
                st.subheader("Last Month Same Period")
            else:
                st.subheader("Last Quarter Same Period")
            
            display_df = sp_comparison[['Salesperson', 'Revenue_previous', 'Orders_previous']].copy()
            display_df.columns = ['Salesperson', 'Revenue', 'Orders']
            st.dataframe(
                display_df.style.format({'Revenue': '${:,.2f}', 'Orders': '{:.0f}'}),
                use_container_width=True,
                hide_index=True
            )
        
        # Salesperson comparison chart
        chart_title = 'Salesperson Revenue Comparison' if period == 'Monthly' else 'Salesperson Revenue Comparison (Quarter)'
        fig = go.Figure(data=[
            go.Bar(name='Current Period', x=sp_comparison['Salesperson'], y=sp_comparison['Revenue_current'], marker_color='#667eea'),
            go.Bar(name='Previous Period', x=sp_comparison['Salesperson'], y=sp_comparison['Revenue_previous'], marker_color='#764ba2')
        ])
        fig.update_layout(
            title=chart_title,
            barmode='group',
            xaxis_tickangle=-45
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Salesperson growth/decline
        st.subheader("Revenue Change by Salesperson")
        display_df = sp_comparison[['Salesperson', 'Revenue_current', 'Revenue_previous', 'Revenue Change', 'Change %']].copy()
        display_df.columns = ['Salesperson', 'Current Revenue', 'Previous Revenue', 'Revenue Change', 'Change %']
        st.dataframe(
            display_df.style.format({
                'Current Revenue': '${:,.2f}',
                'Previous Revenue': '${:,.2f}',
                'Revenue Change': '${:,.2f}',
                'Change %': '{:+.1f}%'
            }),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No salesperson data available for the selected period.")
    
    st.divider()
    
    # Top Products by Revenue
    st.header("📦 Top 10 Products by Revenue")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if period == 'Monthly':
            st.subheader("Month to Date")
        else:
            st.subheader("Quarter to Date")
        current_top_products = get_top_products(current_orders)
        st.dataframe(
            current_top_products.style.format({'Revenue': '${:,.2f}', 'Quantity': '{:,.0f}'}),
            use_container_width=True,
            hide_index=True
        )
    
    with col2:
        if period == 'Monthly':
            st.subheader("Last Month Same Period")
        else:
            st.subheader("Last Quarter Same Period")
        previous_top_products = get_top_products(previous_orders)
        st.dataframe(
            previous_top_products.style.format({'Revenue': '${:,.2f}', 'Quantity': '{:,.0f}'}),
            use_container_width=True,
            hide_index=True
        )
    
    # Product chart
    chart_title = 'Top 10 Products by Revenue - Month to Date' if period == 'Monthly' else 'Top 10 Products by Revenue - Quarter to Date'
    fig = px.bar(
        current_top_products,
        x='Product',
        y='Revenue',
        title=chart_title,
        color='Revenue',
        color_continuous_scale='Greens'
    )
    fig.update_layout(showlegend=False, xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)
    
    st.divider()
    
    # Top Products by Margin
    st.header("💰 Top 10 Products by Total Margin")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if period == 'Monthly':
            st.subheader("Month to Date")
        else:
            st.subheader("Quarter to Date")
        current_top_margin = get_top_products_by_margin(current_orders, products)
        st.dataframe(
            current_top_margin.style.format({
                'Total Margin': '${:,.2f}',
                'Revenue': '${:,.2f}'
            }),
            use_container_width=True,
            hide_index=True
        )
    
    with col2:
        if period == 'Monthly':
            st.subheader("Last Month Same Period")
        else:
            st.subheader("Last Quarter Same Period")
        previous_top_margin = get_top_products_by_margin(previous_orders, products)
        st.dataframe(
            previous_top_margin.style.format({
                'Total Margin': '${:,.2f}',
                'Revenue': '${:,.2f}'
            }),
            use_container_width=True,
            hide_index=True
        )
    
    # Margin chart
    chart_title = 'Top 10 Products by Margin - Month to Date' if period == 'Monthly' else 'Top 10 Products by Margin - Quarter to Date'
    fig = go.Figure(data=[
        go.Bar(name='Total Margin', x=current_top_margin['Product'], y=current_top_margin['Total Margin'], marker_color='lightgreen'),
        go.Bar(name='Revenue', x=current_top_margin['Product'], y=current_top_margin['Revenue'], marker_color='lightblue')
    ])
    fig.update_layout(
        title=chart_title,
        barmode='group',
        xaxis_tickangle=-45
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Footer
    st.divider()
    st.caption(f"📅 Data last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 🔄 Auto-refresh: Every 2 hours")


if __name__ == "__main__":
    main()
