from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import os
import json
from datetime import datetime
import logging
from extract_top_post_urls import extract_top_post_urls
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Create data directory if it doesn't exist
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def process_xls_file(file_path):
    """
    Process XLS file and extract analytics data using pandas.
    Returns structured data that can be stored or analyzed.
    """
    try:
        logger.info(f"Processing XLS file: {file_path}")
        
        # Read the Excel file
        # Try different sheet names that LinkedIn might use
        sheet_names = ['Content Analytics', 'Analytics', 'Sheet1', 0]
        df = None
        
        for sheet in sheet_names:
            try:
                df = pd.read_excel(file_path, sheet_name=sheet)
                logger.info(f"Successfully read sheet: {sheet}")
                break
            except Exception as e:
                logger.warning(f"Could not read sheet {sheet}: {e}")
                continue
        
        if df is None:
            raise Exception("Could not read any sheet from the Excel file")
        
        # Log the structure of the data
        logger.info(f"DataFrame shape: {df.shape}")
        logger.info(f"Columns: {list(df.columns)}")
        logger.info(f"First few rows:\n{df.head()}")
        
        # Extract key metrics (this will need to be customized based on actual file structure)
        processed_data = {
            'file_name': os.path.basename(file_path),
            'processed_at': datetime.now().isoformat(),
            'total_rows': len(df),
            'columns': list(df.columns),
            'data_preview': df.head(5).to_dict('records'),
            'summary_stats': {}
        }
        
        # Try to identify and extract key metrics
        # This is a starting point - you'll need to customize based on actual LinkedIn data structure
        for col in df.columns:
            if df[col].dtype in ['int64', 'float64']:
                processed_data['summary_stats'][col] = {
                    'mean': float(df[col].mean()) if not df[col].isna().all() else None,
                    'max': float(df[col].max()) if not df[col].isna().all() else None,
                    'min': float(df[col].min()) if not df[col].isna().all() else None,
                    'count': int(df[col].count())
                }
        
        # Save processed data to JSON file
        output_file = os.path.join(DATA_DIR, f"processed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(output_file, 'w') as f:
            json.dump(processed_data, f, indent=2)
        
        logger.info(f"Processed data saved to: {output_file}")
        return processed_data
        
    except Exception as e:
        logger.error(f"Error processing XLS file: {e}")
        raise

def extract_author_name(filename):
    name_without_ext = os.path.splitext(filename)[0]
    parts = name_without_ext.split('_')
    if len(parts) >= 3:
        author = parts[-1]
        # Add space before capital letters (except the first character)
        author_formatted = re.sub(r'([a-z])([A-Z])', r'\1 \2', author)
        return author_formatted
    return "Unknown Author"

@app.route('/receive', methods=['POST'])
def receive():
    data = request.get_json()
    logger.info('Received data: %s', data)
    # Store only if it's a scraped_post
    if data and data.get('type') == 'scraped_post':
        entry = {
            'timestamp': datetime.now().isoformat(),
            'url': data.get('url'),
            'data': data.get('data'),
            'publish_date': data.get('publish_date')
        }
        author = data.get('author')
        if author:
            clean_author = author.replace(' ', '_')
            scraped_path = os.path.join(DATA_DIR, f'scraped_posts_{clean_author}.jsonl')
        else:
            scraped_path = os.path.join(DATA_DIR, 'scraped_posts.jsonl')
        with open(scraped_path, 'a') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    return jsonify({'status': 'success', 'received': data}), 200

@app.route('/upload-xls', methods=['POST'])
def upload_xls():
    """
    Upload and process XLS file from the extension.
    """
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            return jsonify({'error': 'File must be an Excel file (.xlsx or .xls)'}), 400
        
        # Save uploaded file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"linkedin_analytics_{timestamp}_{file.filename}"
        file_path = os.path.join(DATA_DIR, filename)
        file.save(file_path)
        
        logger.info(f"File saved: {file_path}")
        
        # Process the file
        processed_data = process_xls_file(file_path)
        
        return jsonify({
            'status': 'success',
            'message': 'File processed successfully',
            'file_name': filename,
            'processed_data': processed_data
        }), 200
        
    except Exception as e:
        logger.error(f"Error in upload_xls: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/get-processed-data', methods=['GET'])
def get_processed_data():
    """
    Get list of processed data files.
    """
    try:
        files = []
        for filename in os.listdir(DATA_DIR):
            if filename.startswith('processed_') and filename.endswith('.json'):
                file_path = os.path.join(DATA_DIR, filename)
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    files.append({
                        'filename': filename,
                        'processed_at': data.get('processed_at'),
                        'file_name': data.get('file_name'),
                        'total_rows': data.get('total_rows')
                    })
        
        return jsonify({
            'status': 'success',
            'files': sorted(files, key=lambda x: x['processed_at'], reverse=True)
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting processed data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/top-posts', methods=['GET'])
def get_top_posts():
    xlsx_file = request.args.get('file')
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    if not xlsx_file:
        # Use the latest XLSX file in backend/data/
        files = [f for f in os.listdir(data_dir) if f.endswith('.xlsx')]
        if not files:
            return jsonify({'error': 'No XLSX files found'}), 404
        files.sort(key=lambda f: os.path.getmtime(os.path.join(data_dir, f)), reverse=True)
        xlsx_file = files[0]
    xlsx_path = os.path.join(data_dir, xlsx_file)
    try:
        result = extract_top_post_urls(xlsx_path)
        author = extract_author_name(xlsx_file)
        result['author'] = author
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/dashboard', methods=['GET'])
def dashboard():
    scraped_path = os.path.join(DATA_DIR, 'scraped_posts.jsonl')
    posts = []
    if os.path.exists(scraped_path):
        with open(scraped_path, 'r') as f:
            for line in f:
                try:
                    posts.append(json.loads(line))
                except Exception:
                    continue
    html = ['<html><head><title>Scraped LinkedIn Posts</title></head><body>']
    html.append('<h2>Scraped LinkedIn Posts</h2>')
    html.append(f'<p>Total posts: {len(posts)}</p>')
    html.append('<table border="1" cellpadding="5"><tr><th>Timestamp</th><th>URL</th><th>Format</th><th>Post Text</th><th>Reactions</th><th>Comments</th></tr>')
    # Show up to 50 most recent posts
    for post in posts[::-1][:50]:
        url = post.get('url', '')
        data = post.get('data', {})
        post_text = (data.get('postText') or '').replace('\n', '<br/>')
        format_ = data.get('format', 'N/A')
        reactions = data.get('reactions')
        reactions_str = ''
        if reactions:
            total = reactions.get('total')
            types = ', '.join([t.get('type','') for t in reactions.get('types',[])])
            reactions_str = f"Total: {total}<br/>Types: {types}"
        comments = data.get('comments',[])
        comments_str = f"{len(comments)}<br/>" + '<br/>'.join([f"<b>{c.get('author','')}</b>: {c.get('text','')}" for c in comments[:3]])
        html.append('<tr><td>{}</td><td><a href="{}" target="_blank">link</a></td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
            post.get('timestamp',''), url, format_, post_text, reactions_str, comments_str))
    html.append('</table></body></html>')
    return ''.join(html)

@app.route('/classified-dashboard', methods=['GET'])
def classified_dashboard():
    classified_path = os.path.join(DATA_DIR, 'classified_posts.jsonl')
    posts = []
    if os.path.exists(classified_path):
        with open(classified_path, 'r') as f:
            for line in f:
                try:
                    posts.append(json.loads(line))
                except Exception:
                    continue
    html = ['<html><head><title>Classified LinkedIn Posts</title></head><body>']
    html.append('<h2>Classified LinkedIn Posts</h2>')
    html.append(f'<p>Total posts: {len(posts)}</p>')
    # Table header
    html.append('<table border="1" cellpadding="5"><tr>'
                '<th>Timestamp</th><th>URL</th><th>Post Text</th>'
                '<th>Format</th><th>Text Tone</th><th>Topic</th><th>Sentiment</th>'
                '<th>Narrative Type</th><th>Content Framework</th>'
                '<th>Call to Action</th><th>Audience Persona</th><th>Length</th>'
                '<th>Hashtags</th><th>Question?</th><th>Storytelling?</th>'
                '<th>Value Proposition</th><th>Engagement Hook?</th>'
                '</tr>')
    # Show up to 50 most recent posts
    for post in posts[::-1][:50]:
        url = post.get('url', '')
        data = post.get('data', {})
        post_text = (data.get('postText') or '').replace('\n', '<br/>')
        classification = post.get('classification', {})
        html.append('<tr>')
        html.append(f'<td>{post.get("timestamp", "")}</td>')
        html.append(f'<td><a href="{url}" target="_blank">link</a></td>')
        html.append(f'<td>{post_text}</td>')
        html.append(f'<td>{classification.get("Format", "")}</td>')
        html.append(f'<td>{classification.get("Text Tone", "")}</td>')
        html.append(f'<td>{classification.get("Topic", "")}</td>')
        html.append(f'<td>{classification.get("Sentiment", "")}</td>')
        html.append(f'<td>{classification.get("Narrative Type", "")}</td>')
        html.append(f'<td>{classification.get("Content Framework", "")}</td>')
        html.append(f'<td>{classification.get("Call to Action", "")}</td>')
        html.append(f'<td>{classification.get("Audience Persona", "")}</td>')
        html.append(f'<td>{classification.get("Length", "")}</td>')
        hashtags = classification.get("Hashtags", [])
        html.append(f'<td>{", ".join(hashtags) if hashtags else ""}</td>')
        html.append(f'<td>{classification.get("Question Present", "")}</td>')
        html.append(f'<td>{classification.get("Storytelling", "")}</td>')
        html.append(f'<td>{classification.get("Value Proposition", "")}</td>')
        html.append(f'<td>{classification.get("Engagement Hook", "")}</td>')
        html.append('</tr>')
    html.append('</table></body></html>')
    return ''.join(html)

if __name__ == '__main__':
    app.run(port=5000, debug=True) 