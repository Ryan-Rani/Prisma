import pandas as pd
import json
import os
from datetime import timedelta, datetime
import matplotlib.pyplot as plt
import numpy as np
from fpdf import FPDF
import warnings
warnings.filterwarnings("ignore", message="Workbook contains no default style, apply openpyxl's default")
import openai
from openai.types.chat import ChatCompletionToolParam

# --- Config ---
DATA_DIR = '../backend/data/'
CLASSIFIED_PATH = os.path.join(DATA_DIR, 'classified_posts.jsonl')
IMG_DIR = 'report_images'
LLM_PROMPT_PATH = 'llm_prompt.txt'

# Cache for latest XLSX file
_latest_xlsx_cache = None

def get_timestamp():
    """Generate a timestamp for filenames and reports"""
    return datetime.now().strftime('%Y%m%d_%H%M%S')

def get_report_filename(author_name=None):
    """Generate report filename with timestamp and author name"""
    timestamp = get_timestamp()
    if author_name:
        # Clean author name for filename (replace spaces with underscores)
        clean_author = author_name.replace(' ', '_')
        return f'reports/linkedin_report_{clean_author}_{timestamp}.pdf'
    return f'reports/linkedin_report_{timestamp}.pdf'

def extract_author_name(filename):
    """Extract author name from analytics filename"""
    # Remove file extension
    name_without_ext = os.path.splitext(filename)[0]
    # Split by underscore and get the last part
    parts = name_without_ext.split('_')
    if len(parts) >= 3:  # Should have at least date_range_author format
        author = parts[-1]  # Last part is the author
        # Convert camel case to space-separated words
        import re
        # Add space before capital letters (except the first character)
        author_formatted = re.sub(r'([a-z])([A-Z])', r'\1 \2', author)
        return author_formatted
    return "Unknown Author"

def find_latest_xlsx():
    """Find the latest XLSX file in the data directory (cached)"""
    global _latest_xlsx_cache
    if _latest_xlsx_cache is not None:
        return _latest_xlsx_cache
    
    if not os.path.exists(DATA_DIR):
        raise FileNotFoundError(f"Data directory not found: {DATA_DIR}")
    
    xlsx_files = []
    for file in os.listdir(DATA_DIR):
        if file.endswith('.xlsx') or file.endswith('.xls'):
            file_path = os.path.join(DATA_DIR, file)
            xlsx_files.append((file_path, os.path.getmtime(file_path)))
    
    if not xlsx_files:
        raise FileNotFoundError(f"No XLSX files found in {DATA_DIR}")
    
    # Sort by modification time (newest first) and return the latest
    xlsx_files.sort(key=lambda x: x[1], reverse=True)
    latest_file = xlsx_files[0][0]
    filename = os.path.basename(latest_file)
    author = extract_author_name(filename)
    print(f"Using latest analytics file: {filename} (Author: {author})")
    _latest_xlsx_cache = latest_file
    return latest_file

def map_analytics_columns(df, mapping):
    """Rename columns in df using the provided mapping if present"""
    for k, v in mapping.items():
        if k in df.columns:
            df = df.rename(columns={k: v})
    return df

# Add at the top of the file, after imports:
SPANISH_TO_ENGLISH = {
    'URL de la publicación': 'Post URL',
    'Fecha de publicación': 'Post publish date',
    'Impresiones': 'Impressions',
    'Interacciones': 'Engagements',
    'Fecha': 'Date',
    'Nuevos seguidores': 'New followers',
}

# Update load_followers and load_top_posts:
def is_spanish_analytics_file(analytics_path):
    filename = os.path.basename(analytics_path)
    if filename.startswith('Contenido_'):
        return True
    # Check for Spanish sheet names
    import pandas as pd
    xl = pd.ExcelFile(analytics_path)
    if 'SEGUIDORES' in xl.sheet_names or 'PUBLICACIONES PRINCIPALES' in xl.sheet_names:
        return True
    return False

def load_followers():
    analytics_path = find_latest_xlsx() # Uses dynamic path
    use_spanish = is_spanish_analytics_file(analytics_path)
    df = pd.read_excel(analytics_path, sheet_name=None)
    # Try both English and Spanish sheet names
    for sheet in ['FOLLOWERS', 'SEGUIDORES']:
        if sheet in df:
            df_followers = df[sheet]
            break
    else:
        raise ValueError('No followers sheet found in analytics file')
    # Use header row 2 (row index 2, i.e., header=2)
    df_followers = pd.read_excel(analytics_path, sheet_name=sheet, header=2)
    df_followers = map_analytics_columns(df_followers, SPANISH_TO_ENGLISH)
    df_followers['Date'] = pd.to_datetime(df_followers['Date'], dayfirst=use_spanish)
    return df_followers

def load_top_posts():
    analytics_path = find_latest_xlsx() # Uses dynamic path
    use_spanish = is_spanish_analytics_file(analytics_path)
    df = pd.read_excel(analytics_path, sheet_name=None)
    # Try both English and Spanish sheet names
    for sheet in ['TOP POSTS', 'PUBLICACIONES PRINCIPALES']:
        if sheet in df:
            df_posts = df[sheet]
            break
    else:
        raise ValueError('No top posts sheet found in analytics file')
    # Use header row 2 (row index 2, i.e., header=2)
    df_posts = pd.read_excel(analytics_path, sheet_name=sheet, header=2)
    df_posts = map_analytics_columns(df_posts, SPANISH_TO_ENGLISH)
    # Rename to 'publish_date' for consistency
    if 'Post publish date' in df_posts.columns:
        df_posts = df_posts.rename(columns={'Post publish date': 'publish_date'})
    # Remove trailing slashes from URLs
    if 'Post URL' in df_posts.columns:
        df_posts['Post URL'] = df_posts['Post URL'].str.rstrip('/')
    df_posts = df_posts[['Post URL', 'publish_date']].dropna()
    df_posts['publish_date'] = pd.to_datetime(df_posts['publish_date'], dayfirst=use_spanish)
    return df_posts

def attribute_follower_gain(df_classified, df_followers, days=3):
    if 'real_publish_date' not in df_classified.columns:
        df_top_posts = load_top_posts()
        # Debug: print types and samples
        print("Classified publish_date dtype:", df_classified['publish_date'].dtype)
        print("Top posts publish_date dtype:", df_top_posts['publish_date'].dtype)
        print("Sample classified publish_date:", df_classified['publish_date'].head())
        print("Sample top posts publish_date:", df_top_posts['publish_date'].head())
        df_classified['url_clean'] = df_classified['url'].str.rstrip('/')
        # Debug: print all column names and their counts
        print("df_top_posts columns:", df_top_posts.columns.tolist())
        print("df_top_posts column counts:", df_top_posts.columns.value_counts())
        # Remove all columns named 'url_clean' and 'Post URL' except the first occurrence
        # This is necessary because duplicate columns from Excel can cause merge errors in pandas.
        cols = df_top_posts.columns.tolist()
        seen = set()
        new_cols = []
        for col in cols:
            if col in ['url_clean', 'Post URL']:
                if col not in seen:
                    new_cols.append(col)
                    seen.add(col)
                # else: skip duplicate
            else:
                new_cols.append(col)
        df_top_posts = df_top_posts.loc[:, new_cols]
        # Now drop url_clean if it still exists
        while 'url_clean' in df_top_posts.columns:
            df_top_posts = df_top_posts.drop(columns=['url_clean'])
        df_top_posts['url_clean'] = df_top_posts['Post URL'].str.rstrip('/')
        print("Classified url_clean sample:", df_classified['url_clean'].head())
        print("Top posts url_clean sample:", df_top_posts['url_clean'].head())
        # Merge on both url_clean and publish_date for robust alignment
        # Print first 5 pairs for both DataFrames
        print("Classified (url_clean, publish_date) pairs (first 5):", list(zip(df_classified['url_clean'], df_classified['publish_date']))[:5])
        print("Top posts (url_clean, real_publish_date) pairs (first 5):", list(zip(df_top_posts['url_clean'], df_top_posts['publish_date']))[:5])
        classified_pairs = set(zip(df_classified['url_clean'], df_classified['publish_date']))
        toppost_pairs = set(zip(df_top_posts['url_clean'], df_top_posts['publish_date']))
        print("Number of classified pairs:", len(classified_pairs))
        print("Number of top post pairs:", len(toppost_pairs))
        print("Number of exact matches:", len(classified_pairs & toppost_pairs))
        # Prepare top posts for merge (do not rename publish_date yet)
        df_top_posts_for_merge = df_top_posts[['url_clean', 'publish_date']]
        # Try merging a small sample
        sample_merge = df_classified[['url_clean', 'publish_date']].head().merge(
            df_top_posts_for_merge,
            on=['url_clean', 'publish_date'], how='left'
        )
        print("Sample merge result:")
        print(sample_merge)
        # Merge for all data
        df_classified = df_classified.merge(
            df_top_posts_for_merge,
            on=['url_clean', 'publish_date'], how='left'
        )
        # Optionally, rename publish_date to real_publish_date after merge
        # df_classified = df_classified.rename(columns={'publish_date': 'real_publish_date'})
        # Check for failed merges
        failed_merge = df_classified[df_classified['publish_date'].isnull()]
        if len(failed_merge) == len(df_classified):
            print("ERROR: All merges failed. No publish_date found for any post. Check date and URL alignment.")
            print(failed_merge[['url_clean', 'publish_date']].head())
            raise RuntimeError("All merges failed: No publish_date found for any post. Check date and URL alignment.")
        elif len(failed_merge) > 0:
            print(f"WARNING: {len(failed_merge)} posts could not be matched to top posts by URL and date. Sample:")
            print(failed_merge[['url_clean', 'publish_date']].head())
    def get_follower_gain(row):
        if pd.isnull(row['publish_date']):
            return 0
        mask = (df_followers['Date'] >= row['publish_date']) & (df_followers['Date'] <= row['publish_date'] + timedelta(days=3))
        return df_followers.loc[mask, 'New followers'].sum()
    df_classified['follower_gain_3d'] = df_classified.apply(get_follower_gain, axis=1)
    return df_classified

# --- Analysis Functions ---
def summarize_by_field(df, field, target='follower_gain_3d'):
    # Use median for typical performance
    median = df.groupby(field)[target].median()
    
    # Add sample size for context
    count = df.groupby(field)[target].count()
    
    # Calculate relative performance vs overall median
    overall_median = df[target].median()
    relative_performance = (median / overall_median).round(2)
    
    # Combine all metrics
    summary = pd.DataFrame({
        'median_followers': median.round(2),
        'post_count': count,
        'relative_performance': relative_performance
    }).sort_values('median_followers', ascending=False)
    
    return summary

def summarize_boolean(df, field, target='follower_gain_3d'):
    # Use median for boolean fields too
    median = df.groupby(field)[target].median()
    
    # Add sample size for context
    count = df.groupby(field)[target].count()
    
    # Calculate relative performance vs overall median
    overall_median = df[target].median()
    relative_performance = (median / overall_median).round(2)
    
    # Combine all metrics
    summary = pd.DataFrame({
        'median_followers': median.round(2),
        'post_count': count,
        'relative_performance': relative_performance
    }).sort_values('median_followers', ascending=False)
    
    return summary

def top_posts_table(df, n=10):
    """Get top n posts by follower gain with enhanced columns"""
    top_posts = df.nlargest(n, 'follower_gain_3d')[['url', 'publish_date', 'follower_gain_3d', 'Topic', 'Text Tone', 'Narrative Type', 'Content Framework']].copy()
    
    # Extract activity ID and create clickable link
    def extract_activity_id(url):
        if pd.isna(url):
            return "N/A"
        # Extract activity ID from LinkedIn URL
        if 'urn:li:activity:' in url:
            activity_id = url.split('urn:li:activity:')[-1].split('/')[0]
            return activity_id
        else:
            # Fallback: just take last part of URL
            return url.split('/')[-1]
    
    # Create clickable activity ID
    top_posts['activity_id'] = top_posts['url'].apply(extract_activity_id)
    
    # Format follower gain
    top_posts['follower_gain_3d'] = top_posts['follower_gain_3d'].round(1)
    
    # Format date to show only date (no time)
    top_posts['publish_date'] = top_posts['publish_date'].dt.strftime('%Y-%m-%d')
    
    # Rename columns for better display
    top_posts = top_posts.rename(columns={
        'url': 'url',  # Keep original URL for PDF links
        'activity_id': 'Post ID',
        'publish_date': 'Date',
        'follower_gain_3d': '+Followers',
        'Topic': 'Topic',
        'Text Tone': 'Tone',
        'Narrative Type': 'Narrative',
        'Content Framework': 'Framework'
    })
    
    return top_posts

def outlier_posts(df, n=3):
    """Get top and bottom n posts by follower gain with enhanced columns"""
    # Get top posts
    top = df.nlargest(n, 'follower_gain_3d')[['url', 'publish_date', 'follower_gain_3d', 'Topic', 'Text Tone', 'Narrative Type', 'Content Framework']].copy()
    
    # Get bottom posts
    bottom = df.nsmallest(n, 'follower_gain_3d')[['url', 'publish_date', 'follower_gain_3d', 'Topic', 'Text Tone', 'Narrative Type', 'Content Framework']].copy()
    
    # Extract activity ID and create clickable link
    def extract_activity_id(url):
        if pd.isna(url):
            return "N/A"
        # Extract activity ID from LinkedIn URL
        if 'urn:li:activity:' in url:
            activity_id = url.split('urn:li:activity:')[-1].split('/')[0]
            return activity_id
        else:
            # Fallback: just take last part of URL
            return url.split('/')[-1]
    
    # Create clickable activity ID
    top['activity_id'] = top['url'].apply(extract_activity_id)
    bottom['activity_id'] = bottom['url'].apply(extract_activity_id)
    
    # Format follower gain
    top['follower_gain_3d'] = top['follower_gain_3d'].round(1)
    bottom['follower_gain_3d'] = bottom['follower_gain_3d'].round(1)
    
    # Format date to show only date (no time)
    top['publish_date'] = top['publish_date'].dt.strftime('%Y-%m-%d')
    bottom['publish_date'] = bottom['publish_date'].dt.strftime('%Y-%m-%d')
    
    # Rename columns for better display
    column_mapping = {
        'url': 'url',  # Keep original URL for PDF links
        'activity_id': 'Post ID',
        'publish_date': 'Date',
        'follower_gain_3d': '+Followers',
        'Topic': 'Topic',
        'Text Tone': 'Tone',
        'Narrative Type': 'Narrative',
        'Content Framework': 'Framework'
    }
    
    top = top.rename(columns=column_mapping)
    bottom = bottom.rename(columns=column_mapping)
    
    return top, bottom

# --- Visualization ---
def save_bar_plot(series, title, filename):
    plt.figure(figsize=(8,4))
    
    # Handle both Series and DataFrame inputs
    if isinstance(series, pd.DataFrame):
        # If it's a DataFrame, use the median_followers column
        if 'median_followers' in series.columns:
            values = series['median_followers'].values
            labels = series.index
        else:
            # Fallback to first numeric column
            numeric_cols = series.select_dtypes(include=[np.number]).columns
            if len(numeric_cols) > 0:
                values = series[numeric_cols[0]].values
                labels = series.index
            else:
                raise ValueError("No numeric columns found in DataFrame")
    else:
        # If it's a Series, use it directly
        values = series.values
        labels = series.index
    
    # Create bar plot without specifying color initially
    bars = plt.bar(range(len(values)), values, alpha=0.8)
    
    # Use different colors for each bar
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', 
              '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9', '#F8C471', '#82E0AA']
    
    # Assign different colors to each bar
    for i, bar in enumerate(bars):
        color_index = i % len(colors)
        bar.set_color(colors[color_index])
    
    plt.title(title)
    plt.ylabel('Avg Follower Gain (3 days)')
    plt.xticks(range(len(labels)), labels, rotation=45)
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()

def generate_visualizations(df, output_dir=IMG_DIR):
    os.makedirs(output_dir, exist_ok=True)
    images = {}
    analyses = [
        ('data.format', 'Follower Gain by Format'),
        ('Topic', 'Follower Gain by Topic'),
        ('Length', 'Follower Gain by Length'),
        ('Text Tone', 'Follower Gain by Text Tone'),
        ('Sentiment', 'Follower Gain by Sentiment'),
        ('Narrative Type', 'Follower Gain by Narrative Type'),
        ('Content Framework', 'Follower Gain by Content Framework'),
        ('Call to Action', 'Follower Gain by Call to Action'),
        ('Audience Persona', 'Follower Gain by Audience Persona'),
    ]
    for field, title in analyses:
        summary = summarize_by_field(df, field)
        img_path = os.path.join(output_dir, f'{field.lower().replace(" ", "_")}.png')
        save_bar_plot(summary, title, img_path)
        images[field] = img_path
    # Boolean fields
    for field, title in [
        ('Engagement Hook', 'Follower Gain by Engagement Hook'),
        ('Storytelling', 'Follower Gain by Storytelling'),
        ('Question Present', 'Follower Gain by Question Present'),
    ]:
        summary = summarize_boolean(df, field)
        img_path = os.path.join(output_dir, f'{field.lower().replace(" ", "_")}.png')
        save_bar_plot(summary, title, img_path)
        images[field] = img_path
    # Hashtags
    df['has_hashtags'] = df['Hashtags'].apply(lambda x: bool(x) and len(x) > 0)
    summary = summarize_boolean(df, 'has_hashtags')
    img_path = os.path.join(output_dir, 'hashtags_present.png')
    save_bar_plot(summary, 'Follower Gain by Hashtags Present', img_path)
    images['Hashtags Present'] = img_path
    return images

# --- PDF Export ---
def clean_text_for_pdf(text):
    # Always convert to string
    text = str(text)
    # Replace en dash and em dash with hyphen
    text = text.replace('–', '-').replace('—', '-')
    # Replace curly quotes with straight quotes
    text = text.replace('"', '"').replace("'", "'")
    # Remove or replace any other non-latin-1 characters
    text = text.encode('latin-1', 'replace').decode('latin-1')
    return text

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'Prisma - LinkedIn Content Performance Report', ln=True, align='C')
        self.ln(5)

    def section_title(self, title):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, clean_text_for_pdf(title), ln=True)
        self.ln(2)

    def section_text(self, text):
        self.set_font('Arial', '', 10)
        self.multi_cell(0, 6, clean_text_for_pdf(text))
        self.ln(2)

    def section_image(self, img_path, w=120):
        self.image(img_path, w=w)
        self.ln(5)

    def add_table(self, df, url_col='', max_url_len=30):
        self.set_font('Arial', 'B', 9)
        col_names = list(df.columns)
        has_url = url_col and url_col in col_names
        if has_url:
            col_names = [c for c in df.columns if c != url_col]
            self.cell(40, 6, 'URL', border=1)
        for col in col_names:
            self.cell(28, 6, clean_text_for_pdf(str(col)[:14]), border=1)
        self.ln()
        self.set_font('Arial', '', 8)
        for _, row in df.iterrows():
            if has_url:
                url = str(row[url_col])
                display_url = url[:max_url_len] + '...' if len(url) > max_url_len else url
                display_url = clean_text_for_pdf(display_url)
                self.set_text_color(0,0,255)
                self.cell(40, 6, display_url, border=1, link=url)
                self.set_text_color(0,0,0)
            for col in col_names:
                val = clean_text_for_pdf(str(row[col]))[:18]
                self.cell(28, 6, val, border=1)
            self.ln()
        self.ln(2)

    def add_table_with_clickable_ids(self, df, url_col='url', id_col='Post ID'):
        """Add table where the ID column is clickable using the URL column"""
        self.set_font('Arial', 'B', 9)
        col_names = [col for col in df.columns if col != url_col]  # Exclude URL column from display
        
        # Reorder columns to put Post ID first
        if id_col in col_names:
            col_names = [id_col] + [col for col in col_names if col != id_col]
        
        # Calculate column widths based on content
        col_widths = {}
        for col in col_names:
            if col == id_col:
                col_widths[col] = 35  # Wider for activity IDs
            elif col == 'Date':
                col_widths[col] = 25  # Date column
            elif col == '+Followers':
                col_widths[col] = 20  # Increased width for +Followers
            else:
                col_widths[col] = 28  # Default width
        
        # Draw headers
        for col in col_names:
            self.cell(col_widths[col], 6, clean_text_for_pdf(str(col)[:14]), border=1)
        self.ln()
        
        # Draw data rows
        self.set_font('Arial', '', 8)
        for _, row in df.iterrows():
            for col in col_names:
                val = clean_text_for_pdf(str(row[col]))[:18]
                
                # Make the ID column clickable
                if col == id_col and url_col in df.columns:
                    url = str(row[url_col])
                    self.set_text_color(0,0,255)
                    self.cell(col_widths[col], 6, val, border=1, link=url)
                    self.set_text_color(0,0,0)
                else:
                    self.cell(col_widths[col], 6, val, border=1)
            self.ln()
        self.ln(2)

    def add_seasonality_table(self, data, title, seasonality_data=None):
        """Add seasonality data as a formatted table with borders"""
        self.set_font('Arial', 'B', 10)
        self.cell(0, 8, title, ln=True)
        self.ln(2)
        
        # Calculate column widths
        col_widths = [60, 40, 30, 30]  # Month/Day, Median, Count, Sum
        
        # Draw headers
        self.set_font('Arial', 'B', 9)
        headers = ['Period', 'Median Gain', 'Posts', 'Total Gain']
        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1)
        self.ln()
        
        # Draw data rows
        self.set_font('Arial', '', 8)
        for index, row in data.iterrows():
            # Skip rows with NaN values
            if pd.isna(row['median']) or pd.isna(row['count']) or pd.isna(row['sum']):
                continue
                
            # Format the period name
            if title.startswith('Monthly'):
                month_names = ['January', 'February', 'March', 'April', 'May', 'June', 
                              'July', 'August', 'September', 'October', 'November', 'December']
                period_name = month_names[index-1]
                # Get actual year from the data
                if seasonality_data and 'merged_data' in seasonality_data:
                    month_posts = seasonality_data['merged_data'][seasonality_data['merged_data']['publish_date'].dt.month == index]
                    if not month_posts.empty:
                        year = month_posts['publish_date'].dt.year.mode().iloc[0]
                        period_display = f"{period_name} {year}"
                    else:
                        period_display = period_name
                else:
                    period_display = period_name
            elif title.startswith('Day'):
                period_display = str(index)
            else:
                period_display = f"Week {index}"
            
            # Format values
            median_val = f"{row['median']:.1f}"
            count_val = f"{int(row['count'])}"
            sum_val = f"{int(row['sum'])}"
            
            # Draw cells
            self.cell(col_widths[0], 6, clean_text_for_pdf(period_display), border=1)
            self.cell(col_widths[1], 6, median_val, border=1)
            self.cell(col_widths[2], 6, count_val, border=1)
            self.cell(col_widths[3], 6, sum_val, border=1)
            self.ln()
        
        self.ln(3)


def export_report_to_pdf(report_text, images, pdf_path=None, top_posts_df=None, outlier_top=None, outlier_bottom=None, winning_formula=None, author_name=None, seasonality_data=None):
    import pandas as pd
    
    if pdf_path is None:
        pdf_path = get_report_filename(author_name)
    pdf = PDF()
    pdf.add_page()
    # Add timestamp and author at the top
    pdf.set_font('Arial', 'I', 10)
    pdf.cell(0, 6, f'Report generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', ln=True)
    if author_name:
        pdf.cell(0, 6, f'Content Creator: {author_name}', ln=True)
    pdf.ln(2)
    # Add Winning Formula section at the top
    print("DEBUG PDF: winning_formula received:", winning_formula)
    print("DEBUG PDF: winning_formula type:", type(winning_formula))
    if winning_formula:
        print("DEBUG PDF: winning_formula keys:", list(winning_formula.keys()) if isinstance(winning_formula, dict) else "Not a dict")
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(0, 10, 'WINNING FORMULA', ln=True, align='C')
        pdf.ln(2)
        
        # Add winning pattern table
        winning_pattern = winning_formula.get('winning_pattern', {})
        if winning_pattern:
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(0, 8, 'Winning Pattern:', ln=True)
            pdf.ln(2)
            
            # Create table headers with better column widths for letter size
            pdf.set_font('Arial', 'B', 9)
            col_widths = [35, 45, 50]  # Category, Winning Value, Data Evidence - optimized for letter size
            pdf.cell(col_widths[0], 6, 'Category', border=1)
            pdf.cell(col_widths[1], 6, 'Winning Value', border=1)
            pdf.cell(col_widths[2], 6, 'Data Evidence', border=1, ln=True)
            
            # Add table rows with smaller font
            pdf.set_font('Arial', '', 8)
            for item in winning_pattern:
                category = clean_text_for_pdf(item["Category"])
                winning_value = clean_text_for_pdf(item["Winning Value"])
                data_evidence = clean_text_for_pdf(item["Data Evidence"])
                
                # Calculate row height based on content
                max_lines = max(
                    len(pdf.multi_cell(col_widths[0], 5, category, border=0, split_only=True)),
                    len(pdf.multi_cell(col_widths[1], 5, winning_value, border=0, split_only=True)),
                    len(pdf.multi_cell(col_widths[2], 5, data_evidence, border=0, split_only=True))
                )
                row_height = max(6, max_lines * 5)
                
                # Draw cells
                pdf.cell(col_widths[0], row_height, category, border=1)
                pdf.cell(col_widths[1], row_height, winning_value, border=1)
                pdf.cell(col_widths[2], row_height, data_evidence, border=1, ln=True)
            
            pdf.ln(5)
        
        # Add key insight
        key_insight = winning_formula.get('key_insight', '')
        if key_insight:
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(0, 8, 'Key Insight:', ln=True)
            pdf.set_font('Arial', '', 11)
            pdf.multi_cell(0, 7, clean_text_for_pdf(key_insight))
            pdf.ln(1)
        
        pdf.ln(5)
    
    # Add seasonality visualizations if available
    if seasonality_data:
        pdf.add_page()
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(0, 10, 'SEASONALITY ANALYSIS', ln=True, align='C')
        pdf.ln(5)
        
        # Generate seasonality visualizations
        monthly = seasonality_data['monthly']
        daily = seasonality_data['daily']
        merged_data = seasonality_data['merged_data']
        
        # Monthly performance chart
        plt.figure(figsize=(10, 6))
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        month_data = monthly.copy()
        month_data.index = [month_names[i-1] for i in monthly.index]
        
        # Create chronological data with year labels
        chronological_data = []
        chronological_labels = []
        
        # Get all unique month-year combinations from actual data
        month_year_combinations = []
        for month_num in monthly.index:
            month_posts = merged_data[merged_data['publish_date'].dt.month == month_num]
            if not month_posts.empty:
                year = month_posts['publish_date'].dt.year.mode().iloc[0]
                month_year_combinations.append((month_num, year, month_data.loc[month_names[month_num-1], 'median']))
        
        # Sort by date (year first, then month)
        month_year_combinations.sort(key=lambda x: (x[1], x[0]))
        
        # Create data for plotting
        for month_num, year, median_val in month_year_combinations:
            chronological_data.append(median_val)
            chronological_labels.append(f"{month_names[month_num-1]} {year}")
        
        # Use different colors for better differentiation
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', 
                 '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9', '#F8C471', '#82E0AA']
        
        # Create bar plot with individual colors for each bar
        bars = plt.bar(range(len(chronological_data)), chronological_data, alpha=0.8)
        
        # Assign different colors to each bar
        for i, bar in enumerate(bars):
            color_index = i % len(colors)
            selected_color = colors[color_index]
            bar.set_color(selected_color)
        
        plt.title('Monthly Follower Gains\n(Median Follower Gain)', fontsize=14, fontweight='bold')
        plt.ylabel('Median Follower Gain (3 days)', fontsize=12)
        plt.xlabel('Month', fontsize=12)
        plt.xticks(range(len(chronological_labels)), chronological_labels, rotation=45)
        
        # Add value labels
        for i, value in enumerate(chronological_data):
            if not pd.isna(value):
                plt.text(i, value + 0.5, f'{value:.1f}', ha='center', va='bottom', fontweight='bold')
        
        plt.tight_layout()
        monthly_chart_path = 'monthly_gains.png'
        plt.savefig(monthly_chart_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        # Day of week chart
        plt.figure(figsize=(10, 6))
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        day_data = daily.reindex(day_order)
        
        # Use distinct colors for each day
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8']
        bars = plt.bar(range(len(day_data)), day_data['median'], alpha=0.8)
        
        # Assign different colors to each bar
        for i, bar in enumerate(bars):
            if not pd.isna(day_data.iloc[i]['median']):
                color_index = i % len(colors)
                selected_color = colors[color_index]
                bar.set_color(selected_color)
        
        plt.title('Follower Gains by Day of Week\n(Median Follower Gain)', fontsize=14, fontweight='bold')
        plt.ylabel('Median Follower Gain (3 days)', fontsize=12)
        plt.xlabel('Day of Week', fontsize=12)
        plt.xticks(range(len(day_data)), day_data.index, rotation=45)
        
        # Add post count labels
        for i, (day, data) in enumerate(day_data.iterrows()):
            if not pd.isna(data['median']):
                plt.text(i, data['median'] + 0.5, f"n={int(data['count'])}", 
                        ha='center', va='bottom', fontweight='bold')
        
        plt.tight_layout()
        daily_chart_path = 'daily_gains.png'
        plt.savefig(daily_chart_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        # Timeline chart with dual y-axis
        fig, ax1 = plt.subplots(figsize=(12, 6))
        df_sorted = merged_data.sort_values('publish_date')
        
        # Individual gains scatter (left y-axis)
        scatter = ax1.scatter(df_sorted['publish_date'], df_sorted['follower_gain_3d'], 
                            s=50, alpha=0.7, c=df_sorted['follower_gain_3d'], cmap='viridis', label='Individual Gains')
        ax1.set_ylabel('Individual Follower Gain (3 days)', fontsize=12, color='blue')
        ax1.tick_params(axis='y', labelcolor='blue')
        
        # Cumulative line (right y-axis)
        ax2 = ax1.twinx()
        df_sorted['cumulative_followers'] = df_sorted['follower_gain_3d'].cumsum()
        ax2.plot(df_sorted['publish_date'], df_sorted['cumulative_followers'], 
                color='red', linewidth=3, alpha=0.8, label='Cumulative Followers')
        ax2.set_ylabel('Cumulative Followers', fontsize=12, color='red')
        ax2.tick_params(axis='y', labelcolor='red')
        
        plt.title('Follower Gains Over Time\n(Individual Posts + Cumulative Growth)', fontsize=14, fontweight='bold')
        ax1.set_xlabel('Post Date', fontsize=12)
        ax1.tick_params(axis='x', rotation=45)
        
        # Add legends
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
        
        plt.tight_layout()
        timeline_chart_path = 'timeline_gains.png'
        plt.savefig(timeline_chart_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        # Add charts to PDF
        pdf.section_image(monthly_chart_path, w=150)
        pdf.ln(5)
        pdf.section_image(daily_chart_path, w=150)
        pdf.ln(5)
        pdf.section_image(timeline_chart_path, w=150)
        
        # Add seasonality tables
        pdf.ln(10)
        pdf.add_seasonality_table(monthly.sort_values('median', ascending=False), 'Monthly Follower Gains', seasonality_data)
        pdf.add_seasonality_table(daily.reindex(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']), 'Daily Follower Gains', seasonality_data)
        
        # Clean up temporary files
        for file in [monthly_chart_path, daily_chart_path, timeline_chart_path]:
            if os.path.exists(file):
                os.remove(file)
    
    # Process the rest of the report
    sections = report_text.split('\n\n')
    
    # Filter out seasonality sections from PDF processing (but keep for LLM)
    filtered_sections = []
    for section in sections:
        if not section.strip():
            continue
        lines = section.strip().split('\n')
        if lines:
            title = lines[0]
            # Skip seasonality sections in PDF processing
            if (title.startswith('SEASONALITY ANALYSIS') or 
                any(title.startswith(subsection) for subsection in [
                    'Monthly Follower Gains:', 'Follower Gains by Day of Week:', 'Top 5 Weeks for Follower Gains:'
                ])):
                continue
        filtered_sections.append(section)
    
    summary_fields = {
        '1. Follower Gain by Format:': 'data.format',
        '2. Follower Gain by Topic:': 'Topic',
        '3. Follower Gain by Length:': 'Length',
        '4. Follower Gain by Text Tone:': 'Text Tone',
        '5. Follower Gain by Sentiment:': 'Sentiment',
        '6. Follower Gain by Narrative Type:': 'Narrative Type',
        '7. Follower Gain by Content Framework:': 'Content Framework',
        '8. Follower Gain by Engagement Hook:': 'Engagement Hook',
        '9. Follower Gain by Storytelling:': 'Storytelling',
        '10. Follower Gain by Call to Action:': 'Call to Action',
        '11. Follower Gain by Audience Persona:': 'Audience Persona',
        '12. Follower Gain by Question Present:': 'Question Present',
        '13. Follower Gain by Hashtags Present:': 'Hashtags Present',
    }
    
    def summary_to_df(series, colname):
        # Handle the new DataFrame structure
        if isinstance(series, pd.DataFrame):
            # New structure with median, post_count, relative_performance
            df = series.reset_index()
            df.columns = [colname, 'Median Followers', 'Post Count', 'Relative Performance']
            # Format relative performance as multiplier
            df['Relative Performance'] = df['Relative Performance'].apply(lambda x: f"{x:.1f}x" if x > 0 else "N/A")
            return df
        else:
            # Old structure (fallback)
            df = series.reset_index()
            df.columns = [colname, 'Median Follower Gain (3d)']
            return df
    
    df_classified = load_classified()
    df_followers = load_followers()
    df_classified = attribute_follower_gain(df_classified, df_followers)
    summaries = {
        'data.format': summary_to_df(summarize_by_field(df_classified, 'data.format'), 'data.format'),
        'Topic': summary_to_df(summarize_by_field(df_classified, 'Topic'), 'Topic'),
        'Length': summary_to_df(summarize_by_field(df_classified, 'Length'), 'Length'),
        'Text Tone': summary_to_df(summarize_by_field(df_classified, 'Text Tone'), 'Text Tone'),
        'Sentiment': summary_to_df(summarize_by_field(df_classified, 'Sentiment'), 'Sentiment'),
        'Narrative Type': summary_to_df(summarize_by_field(df_classified, 'Narrative Type'), 'Narrative Type'),
        'Content Framework': summary_to_df(summarize_by_field(df_classified, 'Content Framework'), 'Content Framework'),
        'Engagement Hook': summary_to_df(summarize_boolean(df_classified, 'Engagement Hook'), 'Engagement Hook'),
        'Storytelling': summary_to_df(summarize_boolean(df_classified, 'Storytelling'), 'Storytelling'),
        'Call to Action': summary_to_df(summarize_by_field(df_classified, 'Call to Action'), 'Call to Action'),
        'Audience Persona': summary_to_df(summarize_by_field(df_classified, 'Audience Persona'), 'Audience Persona'),
        'Question Present': summary_to_df(summarize_boolean(df_classified, 'Question Present'), 'Question Present'),
        'Hashtags Present': summary_to_df(summarize_boolean(df_classified.assign(has_hashtags=df_classified['Hashtags'].apply(lambda x: bool(x) and len(x) > 0)), 'has_hashtags'), 'Hashtags Present'),
    }
    
    for section in filtered_sections:
        if not section.strip():
            continue
        lines = section.strip().split('\n')
        if lines:
            title = lines[0]
            
            # Add page break before major sections
            if any(keyword in title for keyword in ['Top Posts', 'Top 3 Posts', 'Bottom 3 Posts', 'SEASONALITY ANALYSIS', 
                                                   'Follower Gain by Format', 'Follower Gain by Topic', 'Follower Gain by Length',
                                                   'Follower Gain by Text Tone', 'Follower Gain by Sentiment', 'Follower Gain by Narrative Type',
                                                   'Follower Gain by Content Framework', 'Follower Gain by Engagement Hook', 'Follower Gain by Storytelling',
                                                   'Follower Gain by Call to Action', 'Follower Gain by Audience Persona', 'Follower Gain by Question Present',
                                                   'Follower Gain by Hashtags Present']):
                pdf.add_page()
            
            pdf.section_title(title)
            # Render as table if in summary_fields
            if title in summary_fields:
                field = summary_fields[title]
                if field == 'seasonality':
                    # Skip seasonality section as it's handled above
                    continue
                elif field in summaries:
                    pdf.add_table(summaries[field], url_col='')
                else:
                    pdf.section_text('\n'.join(lines[1:]))
            elif title.startswith('14. Top Posts by Follower Gain:') and top_posts_df is not None:
                if 'url' in top_posts_df.columns:
                    pdf.add_table_with_clickable_ids(top_posts_df, url_col='url', id_col='Post ID')
                else:
                    pdf.add_table(top_posts_df, url_col='')
            elif title.startswith('15. Top 3 Posts:') and outlier_top is not None and outlier_bottom is not None:
                pdf.section_title('Top 3 Posts')
                if 'url' in outlier_top.columns:
                    pdf.add_table_with_clickable_ids(outlier_top, url_col='url', id_col='Post ID')
                else:
                    pdf.add_table(outlier_top, url_col='')
            elif title.startswith('16. Bottom 3 Posts:') and outlier_top is not None and outlier_bottom is not None:
                pdf.section_title('Bottom 3 Posts')
                if 'url' in outlier_bottom.columns:
                    pdf.add_table_with_clickable_ids(outlier_bottom, url_col='url', id_col='Post ID')
                else:
                    pdf.add_table(outlier_bottom, url_col='')
            else:
                pdf.section_text('\n'.join(lines[1:]))
            for key, img_path in images.items():
                if key.lower() in title.lower():
                    pdf.section_image(img_path)
    pdf.output(pdf_path)

# --- LLM Prompt Generation ---
def build_llm_prompt(report_text, top_posts_table):
    prompt = f'''
You are a LinkedIn content strategy expert. Below is a detailed analytics report for a content creator, including summary statistics and top-performing post features.

Report:
{report_text}

Top Posts Table:
{top_posts_table.to_string()}

Based on this data, provide:
- 3-5 actionable recommendations to maximize follower growth
- A summary of the "winning formula" for this creator
- Any content types or strategies to avoid

Be specific and use the data to justify your advice.
'''
    return prompt

# --- Centralized Winning Formula Schema ---
WINNING_FORMULA_SCHEMA_DICT = {
    "winning_pattern": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "Category": {"type": "string", "description": "Content characteristic category"},
                "Winning Value": {"type": "string", "description": "Most effective value for this category"},
                "Data Evidence": {"type": "string", "description": "Specific data reference supporting this value"}
            },
            "required": ["Category", "Winning Value", "Data Evidence"]
        }
    },
    "key_insight": {"type": "string", "description": "One specific, actionable insight about the most important pattern"}
}

# --- LLM Function Tool Param ---
WINNING_FORMULA_TOOL = [
    ChatCompletionToolParam(
        type="function",
        function={
            "name": "generate_winning_formula",
            "description": "Generate a concise winning pattern summary showing the most effective content characteristics based on analytics data.",
            "parameters": {
                "type": "object",
                "properties": WINNING_FORMULA_SCHEMA_DICT,
                "required": ["winning_pattern", "key_insight"]
            }
        }
    )
]

# --- Prompt Template ---
def build_winning_formula_prompt(report_text, top_posts_table, author_name=None):
    prompt = f"""
You are a LinkedIn content strategy expert analyzing comprehensive performance data to identify winning content patterns and create strategic insights.

CREATOR NAME: {author_name if author_name else "Unknown Creator"}

TASK: Create a concise "Winning Pattern" table showing the most effective content characteristics, then synthesize a strategic key insight that combines multiple data dimensions.

REQUIRED OUTPUT STRUCTURE:
{{
  "winning_pattern": [
    {{
      "Category": "Content Format",
      "Winning Value": "Most effective format - be specific (e.g., 'Carousel posts', 'Video under 60s', 'Text-only with bullet points', 'Image with caption')",
      "Data Evidence": "Use actual data to show performance vs the typical post (e.g., 'X% better than the typical post', 'X% better than Y format')"
    }},
    {{
      "Category": "Text Tone",
      "Winning Value": "Most effective tone - be specific (e.g., 'Conversational, Data-driven', 'Personal storytelling', 'Authoritative but friendly')",
      "Data Evidence": "Use actual data to show performance vs the typical post (e.g., 'X% better than the typical post', 'X% better than Y tone')"
    }},
    {{
      "Category": "Topic Focus",
      "Winning Value": "Most effective topics - be specific (e.g., 'Career transitions', 'Industry insights', 'Product launches', 'Behind-the-scenes')",
      "Data Evidence": "Use actual data to show performance vs the typical post (e.g., 'X% better than the typical post', 'X% better than Y topic')"
    }},
    {{
      "Category": "Narrative Style",
      "Winning Value": "Most effective narrative - be specific (e.g., 'Before/after stories', 'Behind-the-scenes', 'Data insights', 'Personal challenges')",
      "Data Evidence": "Use actual data to show performance vs the typical post (e.g., 'X% better than the typical post', 'X% better than Y narrative')"
    }},
    {{
      "Category": "Call to Action",
      "Winning Value": "Most effective CTA - be specific (e.g., 'Ask a question', 'Share experience', 'Follow for more', 'Comment below')",
      "Data Evidence": "Use actual data to show performance vs the typical post (e.g., 'X% better than the typical post', 'X% better than Y CTA')"
    }},
    {{
      "Category": "Content Framework",
      "Winning Value": "Most effective framework - be specific (e.g., 'Problem-Solution', 'Story-Lesson', 'How-to guide', 'Listicle')",
      "Data Evidence": "Use actual data to show performance vs the typical post (e.g., 'X% better than the typical post', 'X% better than Y framework')"
    }}
  ],
  "key_insight": "MUST follow this exact format: 'Data indicates [Creator Name] should prioritize [specific content strategy] with [exact evidence and percentages]. Analysis shows [best posting day] performs [X%] better than average, while [specific month] had [pre-calculated percentage] higher gains indicating external factors. Evidence suggests [content structure pattern] drives [specific outcome].' Use ONLY pre-calculated percentages from the seasonality data, never calculate or invent percentages. Use precise, data-driven language."
}}

CRITICAL REQUIREMENTS:

1. **PERSONALIZATION**: 
   - Extract the creator's actual name from the report data
   - Use the real name directly, not '[Creator Name]' placeholder
   - NEVER use generic terms like "LinkedIn creators" or "content creators"

2. **DATA VALIDATION**:
   - Use ONLY exact percentages/numbers that appear in the analysis report
   - NEVER calculate, estimate, or invent percentages
   - If a specific percentage isn't in the report, skip that data point
   - Only use follower gain data, NOT engagement data (we don't have engagement analysis yet)
   - Use ONLY pre-calculated percentages from the seasonality data (e.g., "+84% vs average", "-12% vs average")
   - If no specific percentage exists in the data, don't mention percentages

3. **SEASONALITY INTEGRATION**:
   - MUST include timing insights from seasonality data
   - Reference specific days/times with actual percentages from the report
   - Use monthly, daily, and weekly seasonality patterns
   - Only use percentages that appear explicitly in the seasonality analysis
   - Focus on identifying patterns that could indicate external factors (conferences, campaigns, events)
   - Instead of "post in October", say "October shows +84% higher gains, suggesting external factors like conferences or campaigns"
   - IDENTIFY THE BEST POSTING DAY: Look at the daily data and find the day with the highest percentage vs average
   - Use the exact pre-calculated percentage for the best day (e.g., "Tuesday performs -12% vs average")
   - If all days perform below average, mention the least negative day

4. **MULTI-DIMENSIONAL SYNTHESIS**:
   - MUST combine at least 3 different data dimensions
   - Include: timing (seasonality) + content structure + follower gain patterns
   - Reference specific narrative types, frameworks, and content tactics
   - Connect patterns from top-performing posts
   - Focus ONLY on follower gain data, not engagement

5. **SPECIFIC FORMAT**:
   - Start with actual creator name and main content strategy
   - Include timing recommendation with seasonality data
   - Add content structure pattern insights
   - End with specific content recommendations
   - Use actual percentages throughout
   - Remove all references to "engagement" or "follower engagement"

STRATEGIC ANALYSIS GUIDELINES:

1. **Multi-Dimensional Synthesis**: Combine insights from:
   - **Seasonality patterns** (best posting times/days/months)
   - **Content structure** (narrative types, frameworks, content hooks)
   - **Follower gain patterns** (what drives follower growth)
   - **Performance outliers** (what makes top posts special)
   - **Content patterns** (questions, hashtags, hooks)

2. **Strategic Questions to Answer**:
   - **When** should they post? (seasonality data)
   - **How** should they structure content? (narrative + framework patterns)
   - **What** topics/formats work best? (existing analysis)
   - **Why** do certain combinations work? (follower gain patterns)
   - **Where** are the biggest opportunities? (performance gaps)

3. **Key Insight Structure**:
   - Start with the strongest content combination
   - Add timing strategy from seasonality
   - Include content optimization tactics
   - Reference specific performance data with percentages
   - End with actionable next steps

4. **Data Integration**:
   - Use seasonality data for timing recommendations
   - Combine narrative + framework patterns for content structure
   - Reference content patterns (questions, hooks, storytelling)
   - Include outlier analysis from top posts
   - Use actual percentages from relative performance data

5. **SCIENTIFIC TONE REQUIREMENTS**:
   - Use empirical, data-driven language
   - Focus on statistical evidence rather than subjective opinions
   - Use precise terminology: "data indicates", "analysis shows", "evidence suggests"
   - Avoid conversational phrases like "leads to", "because it", "can enhance", "reveals opportunity"
   - Structure insights as: "Data indicates [pattern] with [specific evidence]"
   - Use objective language: "performs X% better" not "leads to X% better"
   - Use precise verbs: "drives", "indicates", "performs", "achieves"
   - Identify the BEST posting day from the daily data and use its exact percentage
   - Use "prioritize" instead of "focus on" for stronger action language

ANALYSIS GUIDELINES:
- Analyze the top performing posts to identify the most common successful characteristics
- For each category, provide the most effective value and supporting data evidence
- Focus on patterns that appear consistently in high-performing content
- Be SPECIFIC and ACTIONABLE - avoid generic terms like "Text with video", "Other", or "Long"
- Use concrete examples and measurable characteristics
- Data Evidence should use ACTUAL DATA from the analysis report, not invented numbers
- Look for categories with relative_performance > 1.0 (better than the typical post)
- Convert relative performance to percentages: (relative_performance - 1) * 100
- Use the actual relative performance data from the analysis

CATCH-ALL CATEGORY STRATEGY:
- Catch-all categories ("Neutral", "Other", "Mixed", "Generic", "No clear pattern", "Unspecified") are non-actionable
- If a catch-all category has the highest performance, look for the NEXT BEST specific category
- If only catch-all categories exist for a field, skip that category entirely
- When comparing specific categories to catch-alls, use the catch-all as baseline: "X% better than Neutral posts"
- Prioritize categories with specific, actionable values over catch-all categories
- If a catch-all has high performance but low sample size (<5 posts), treat it as noise and skip
- Focus on categories where specific patterns clearly outperform catch-all categories
- ALWAYS skip "Other" category regardless of performance - it's not actionable
- For Call to Action, if "Other" is highest, use the next best specific CTA (e.g., "Comment")

QUALITY CHECKS:
- Ensure tone and sentiment are consistent
- Prioritize insights that creators can actually implement
- AVOID generic terms: "Text with video" (too broad), "Other" (not actionable), "Long" (not specific)
- Focus on DISTINCTIVE characteristics that set winning posts apart
- Key Insight should reference actual data patterns with percentages
- Use the strongest pattern combinations with their actual performance data
- Convert multipliers to percentages for user-friendly language
- Skip entire categories where only catch-all categories exist or have insufficient data
- Key Insight must synthesize multiple data dimensions, not just format+topic+tone
- MUST include seasonality timing recommendations
- MUST use actual creator name from report data
- MUST cite specific percentages from the data
- MUST combine at least 3 different data dimensions
- MUST focus only on follower gain data, NOT engagement
- MUST use only exact percentages from the report, never calculate or invent

DATA TO ANALYZE:
{report_text}

TOP PERFORMING POSTS:
{top_posts_table.to_string(index=False)}

Return ONLY the JSON object, no extra text or formatting.
"""
    return prompt

import re
def clean_recommendation(rec):
    return re.sub(r'^[\d\.-]+\s*', '', rec).strip()

def recommendation_has_number(rec):
    return bool(re.search(r'\d', rec))

def get_winning_formula_llm(prompt, model='gpt-4-turbo'):
    response = openai.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        tools=WINNING_FORMULA_TOOL,
        tool_choice={"type": "function", "function": {"name": "generate_winning_formula"}},
        temperature=0.3
    )
    message = response.choices[0].message
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls and len(tool_calls) > 0:
        arguments = tool_calls[0].function.arguments
        import json as _json
        result = _json.loads(arguments)
        return result
    else:
        return {
            "winning_pattern": [
                {
                    "Category": "No clear pattern",
                    "Winning Value": "No clear pattern",
                    "Data Evidence": "Insufficient data"
                }
            ],
            "key_insight": "Insufficient data to identify clear patterns"
        }

def analyze_seasonality(df_classified, df_followers):
    """Analyze seasonality patterns in follower gains"""
    # Merge datasets
    df_merged = df_classified.merge(df_followers, left_on='publish_date', right_on='Date', how='left')
    
    # Calculate follower gains
    df_followers['cumulative_followers'] = df_followers['New followers'].cumsum()
    
    def calculate_follower_gain(row, df_followers, days=3):
        post_date = row['publish_date']
        future_date = post_date + timedelta(days=days)
        
        current_data = df_followers[df_followers['Date'] <= post_date]
        current_followers = current_data['cumulative_followers'].iloc[-1] if len(current_data) > 0 else 0
        
        future_data = df_followers[df_followers['Date'] <= future_date]
        future_followers = future_data['cumulative_followers'].iloc[-1] if len(future_data) > 0 else 0
        
        return future_followers - current_followers
    
    df_merged['follower_gain_3d'] = df_merged.apply(lambda row: calculate_follower_gain(row, df_followers), axis=1)
    
    # Extract time components
    df_merged['hour'] = df_merged['publish_date'].dt.hour
    df_merged['day_of_week'] = df_merged['publish_date'].dt.day_name()
    df_merged['month'] = df_merged['publish_date'].dt.month
    df_merged['week_of_year'] = df_merged['publish_date'].dt.isocalendar().week
    
    # Monthly analysis
    month_analysis = df_merged.groupby('month')['follower_gain_3d'].agg([
        'count', 'mean', 'median', 'sum'
    ]).round(2)
    
    # Day of week analysis
    day_analysis = df_merged.groupby('day_of_week')['follower_gain_3d'].agg([
        'count', 'mean', 'median', 'sum'
    ]).round(2)
    
    # Week of year analysis
    week_analysis = df_merged.groupby('week_of_year')['follower_gain_3d'].agg([
        'count', 'mean', 'median', 'sum'
    ]).round(2).dropna()
    
    return {
        'monthly': month_analysis,
        'daily': day_analysis,
        'weekly': week_analysis,
        'merged_data': df_merged
    }

def generate_seasonality_text(seasonality_data):
    """Generate text summary of seasonality analysis with pre-calculated percentages"""
    monthly = seasonality_data['monthly']
    daily = seasonality_data['daily']
    weekly = seasonality_data['weekly']
    merged_data = seasonality_data['merged_data']
    
    # Calculate overall median for percentage comparisons
    overall_median = merged_data['follower_gain_3d'].median()
    
    text = "SEASONALITY ANALYSIS\n\n"
    
    # Monthly analysis with pre-calculated percentages
    text += "Monthly Follower Gains:\n"
    month_names = ['January', 'February', 'March', 'April', 'May', 'June', 
                   'July', 'August', 'September', 'October', 'November', 'December']
    
    for month, data in monthly.sort_values('median', ascending=False).iterrows():
        month_name = month_names[month-1]
        # Get actual year from the data instead of assumptions
        month_posts = merged_data[merged_data['publish_date'].dt.month == month]
        if not month_posts.empty:
            # Get the most common year for this month
            year = month_posts['publish_date'].dt.year.mode().iloc[0] if not month_posts.empty else 2024
            # Pre-calculate percentage
            percentage_diff = ((data['median'] - overall_median) / overall_median) * 100
            text += f"{month_name} {year}: {data['median']:.1f} median followers (n={int(data['count'])}) - {percentage_diff:+.0f}% vs average\n"
        else:
            percentage_diff = ((data['median'] - overall_median) / overall_median) * 100
            text += f"{month_name}: {data['median']:.1f} median followers (n={int(data['count'])}) - {percentage_diff:+.0f}% vs average\n"
    
    text += "\n"
    
    # Day of week analysis with pre-calculated percentages
    text += "Follower Gains by Day of Week:\n"
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    for day in day_order:
        if day in daily.index:
            data = daily.loc[day]
            percentage_diff = ((data['median'] - overall_median) / overall_median) * 100
            text += f"{day}: {data['median']:.1f} median followers (n={int(data['count'])}) - {percentage_diff:+.0f}% vs average\n"
    
    text += "\n"
    
    # Top weeks with pre-calculated percentages
    text += "Top 5 Weeks for Follower Gains:\n"
    top_weeks = weekly.sort_values('median', ascending=False).head(5)
    for week, data in top_weeks.iterrows():
        percentage_diff = ((data['median'] - overall_median) / overall_median) * 100
        text += f"Week {week}: {data['median']:.1f} median followers (n={int(data['count'])}) - {percentage_diff:+.0f}% vs average\n"
    
    return text

# --- Main Entrypoint ---
def get_author_name():
    """Get author name from the latest analytics file"""
    analytics_path = find_latest_xlsx()
    filename = os.path.basename(analytics_path)
    return extract_author_name(filename)

def extract_author_from_latest_xlsx():
    analytics_path = find_latest_xlsx()
    filename = os.path.basename(analytics_path)
    # Remove extension
    filename_no_ext = filename.replace('.xlsx', '').replace('.xls', '')
    # Split on underscores
    parts = filename_no_ext.split('_')
    # English: Content_YYYY-MM-DD_YYYY-MM-DD_AuthorName
    # Spanish: Contenido_YYYY-MM-DD_YYYY-MM-DD_Author Name
    if len(parts) >= 4:
        # Join all parts after the last date as the author (handles spaces)
        author_parts = parts[3:]
        author = ' '.join(author_parts)
        # Add spaces for camel case (if needed)
        import re
        author_spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', author)
        author_spaced = author_spaced.replace('_', ' ').strip()
        return author_spaced
    return None

def load_classified():
    # Try to use classified_posts_{author}.jsonl if it exists
    analytics_path = find_latest_xlsx()
    filename = os.path.basename(analytics_path)
    author = extract_author_from_latest_xlsx()
    if author:
        clean_author = author.replace(' ', '_')
        classified_path = os.path.join(DATA_DIR, f'classified_posts_{clean_author}.jsonl')
        print(f"Trying to load classified file: {classified_path}")
        if os.path.exists(classified_path):
            path_to_use = classified_path
        else:
            # List all available classified_posts files
            import glob
            available = glob.glob(os.path.join(DATA_DIR, 'classified_posts*.jsonl'))
            raise FileNotFoundError(f"Classified file for author '{author}' not found. Looked for: {classified_path}. Available: {available}")
    else:
        import glob
        available = glob.glob(os.path.join(DATA_DIR, 'classified_posts*.jsonl'))
        raise FileNotFoundError(f"Could not infer author from latest analytics file.\nAnalytics filename: {filename}\nextract_author_from_latest_xlsx() returned: {author}\nAvailable classified files: {available}")
    rows = []
    with open(path_to_use, 'r', encoding='utf-8') as f:
        for line in f:
            rows.append(json.loads(line))
    df = pd.json_normalize(rows)
    for col in df.columns:
        if col.startswith('classification.'):
            new_col = col.replace('classification.', '')
            df[new_col] = df[col]
    if 'real_publish_date' in df.columns:
        df['publish_date'] = pd.to_datetime(df['real_publish_date'])
    elif 'publish_date' in df.columns:
        df['publish_date'] = pd.to_datetime(df['publish_date'])
    else:
        df['publish_date'] = pd.to_datetime(df['timestamp'].str[:10])
    return df

def main():
    # Load data
    df_classified = load_classified()
    df_followers = load_followers()
    
    # Get author name
    author_name = get_author_name()
    print(f"Analyzing content for: {author_name}")
    
    # Debug: show available columns
    print(f"Available columns in df_classified: {list(df_classified.columns)}")
    
    # Attribute follower gains
    df_classified = attribute_follower_gain(df_classified, df_followers)
    
    # Analyze seasonality
    seasonality_data = analyze_seasonality(df_classified, df_followers)
    seasonality_text = generate_seasonality_text(seasonality_data)
    
    # Generate report sections
    report_sections = []
    
    # Define summary fields and check which ones exist
    summary_fields = {
        '1. Follower Gain by Format:': 'data.format',
        '2. Follower Gain by Topic:': 'Topic',
        '3. Follower Gain by Length:': 'Length',
        '4. Follower Gain by Text Tone:': 'Text Tone',
        '5. Follower Gain by Sentiment:': 'Sentiment',
        '6. Follower Gain by Narrative Type:': 'Narrative Type',
        '7. Follower Gain by Content Framework:': 'Content Framework',
        '8. Follower Gain by Engagement Hook:': 'Engagement Hook',
        '9. Follower Gain by Storytelling:': 'Storytelling',
        '10. Follower Gain by Call to Action:': 'Call to Action',
        '11. Follower Gain by Audience Persona:': 'Audience Persona',
        '12. Follower Gain by Question Present:': 'Question Present',
        '13. Follower Gain by Hashtags Present:': 'Hashtags Present',
    }
    
    # Check which fields exist in the DataFrame
    available_fields = []
    for title, field in summary_fields.items():
        if field == 'data.format':
            if 'data.format' in df_classified.columns:
                available_fields.append((title, field))
        elif field in ['Engagement Hook', 'Storytelling', 'Question Present']:
            if field in df_classified.columns:
                available_fields.append((title, field))
        elif field == 'Hashtags Present':
            # Handle hashtags specially - check if Hashtags column exists
            if 'Hashtags' in df_classified.columns:
                available_fields.append((title, field))
        else:
            if field in df_classified.columns:
                available_fields.append((title, field))
    
    # Process only available fields
    for title, field in available_fields:
        if field == 'data.format':
            summary = summarize_by_field(df_classified, 'data.format')
        elif field in ['Engagement Hook', 'Storytelling', 'Question Present']:
            summary = summarize_boolean(df_classified, field)
        elif field == 'Hashtags Present':
            # Create hashtags present field
            df_classified['has_hashtags'] = df_classified['Hashtags'].apply(lambda x: bool(x) and len(x) > 0)
            summary = summarize_boolean(df_classified, 'has_hashtags')
        else:
            summary = summarize_by_field(df_classified, field)
        
        section_text = f"{title}\n{summary.to_string()}\n"
        report_sections.append(section_text)
    
    # Add top posts
    top_posts = top_posts_table(df_classified)
    top_posts_section = f"14. Top Posts by Follower Gain:\n{top_posts.to_string(index=False)}\n"
    report_sections.append(top_posts_section)
    
    # Add outlier posts
    top, bottom = outlier_posts(df_classified)
    top_outlier_section = f"15. Top 3 Posts:\n{top.to_string(index=False)}\n"
    bottom_outlier_section = f"16. Bottom 3 Posts:\n{bottom.to_string(index=False)}\n"
    report_sections.append(top_outlier_section)
    report_sections.append(bottom_outlier_section)
    
    # Add seasonality analysis
    report_sections.append(seasonality_text)
    
    # Combine all sections
    report_text = '\n\n'.join(report_sections)
    
    # Generate winning formula
    llm_prompt = build_winning_formula_prompt(report_text, top_posts, author_name)
    llm_result = get_winning_formula_llm(llm_prompt)
    
    # Extract winning pattern and key insight
    winning_pattern = llm_result.get('winning_pattern', [])
    key_insight = llm_result.get('key_insight', '')
    
    # Format for text report (new structure)
    timestamp = get_timestamp()
    winning_section = f'Report generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n'
    winning_section += 'WINNING FORMULA\n\n'
    
    # Add overall median for context
    overall_median = df_classified['follower_gain_3d'].median()
    winning_section += f"Overall Median Follower Gain (3 days): {overall_median:.2f}\n\n"
    
    # Add winning pattern table
    if winning_pattern:
        winning_section += 'Winning Pattern:\n'
        for item in winning_pattern:
            winning_section += f'{item["Category"]}\n'
            winning_section += f'Winning Value: {item["Winning Value"]}\n'
            winning_section += f'Data Evidence: {item["Data Evidence"]}\n'
            winning_section += '\n'
    
    # Add key insight
    if key_insight:
        winning_section += f'Key Insight: {key_insight}\n\n'
    
    final_report = winning_section + report_text
    # Generate text filename with author name in reports directory
    clean_author = author_name.replace(' ', '_') if author_name else ''
    text_filename = f'reports/linkedin_report_{clean_author}_{timestamp}.txt' if clean_author else f'reports/linkedin_report_{timestamp}.txt'
    
    # Ensure reports directory exists
    os.makedirs('reports', exist_ok=True)
    
    with open(text_filename, 'w', encoding='utf-8') as f:
        f.write(final_report)
    images = generate_visualizations(df_classified)
    
    # Debug: show top posts info
    print(f"Top posts shape: {top_posts.shape}")
    print(f"Top posts columns: {list(top_posts.columns)}")
    print(f"Sample top posts: {top_posts.head(2).to_dict('records')}")
    
    # Only pass the original report_text to the PDF export to avoid duplication
    pdf_filename = f'reports/linkedin_report_{clean_author}_{timestamp}.pdf' if clean_author else f'reports/linkedin_report_{timestamp}.pdf'
    export_report_to_pdf(report_text, images, pdf_path=pdf_filename, top_posts_df=top_posts, outlier_top=top, outlier_bottom=bottom, winning_formula=llm_result, author_name=author_name, seasonality_data=seasonality_data)
    with open(LLM_PROMPT_PATH, 'w', encoding='utf-8') as f:
        f.write(llm_prompt)
    print(f"LLM prompt saved to {LLM_PROMPT_PATH}")
    print(f"📄 Text report: {text_filename}")
    print(f"📊 PDF report: {pdf_filename}")

if __name__ == "__main__":
    main() 