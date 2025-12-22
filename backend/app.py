from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from sqlalchemy.orm import Session
from models import init_db, get_session, Website, Page, Generation, ChangeLog
from crawler import WebCrawler
from generator import LLMsTxtGenerator
from monitor import ChangeMonitor
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from dotenv import load_dotenv
import io
import os
import logging

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def validate_environment():
    """Validate required environment variables and provide helpful error messages"""
    errors = []
    
    openai_key = os.getenv('OPENAI_API_KEY')
    if openai_key and not openai_key.startswith('sk-'):
        logger.warning("OPENAI_API_KEY format appears invalid (should start with 'sk-')")
    
    if errors:
        error_msg = "\n".join(errors)
        raise ValueError(f"Environment validation failed:\n{error_msg}")
    
    logger.info("Environment variables validated successfully")

try:
    validate_environment()
except ValueError as e:
    logger.error(str(e))
    raise

app = Flask(__name__)
CORS(app)

db_path = os.getenv('DB_PATH', 'database.db')
engine = init_db(db_path)

scheduler = BackgroundScheduler()
scheduler.start()

def get_db_session():
    return get_session(engine)

def check_monitored_websites():
    """Background job to check monitored websites"""
    with app.app_context():
        try:
            session = get_db_session()
            monitor = ChangeMonitor(session)
            monitor.check_all_monitored_websites()
            session.close()
        except Exception as e:
            logger.error(f"Error in background monitoring job: {e}")

scheduler.add_job(
    func=check_monitored_websites,
    trigger="interval",
    minutes=15,
    id='check_websites',
    name='Check monitored websites',
    replace_existing=True
)

@app.route('/api/generate', methods=['POST'])
def generate_llms_txt():
    """Generate llms.txt for a website"""
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        logger.info(f"Generating llms.txt for {url}")
        
        try:
            crawler = WebCrawler(url, max_depth=3, max_pages=100, delay=0.1, use_llm=False)
            pages = crawler.crawl()
            
            if not pages:
                logger.warning(f"No pages found for {url}")
                return jsonify({
                    'error': 'No pages found on the website. This could be due to: robots.txt restrictions, authentication required, or the website blocking crawlers.'
                }), 404
        except Exception as e:
            logger.error(f"Error crawling {url}: {e}")
            return jsonify({'error': f'Error crawling website: {str(e)}'}), 500
        
        generator = LLMsTxtGenerator(use_llm=True)
        llms_content = generator.generate(pages)
        
        session = get_db_session()
        try:
            website = session.query(Website).filter(Website.url == url).first()
            if not website:
                website = Website(url=url, status='completed')
                session.add(website)
                session.commit()
                session.refresh(website)
            
            for page_data in pages:
                page = Page(
                    website_id=website.id,
                    url=page_data['url'],
                    title=page_data.get('title'),
                    description=page_data.get('description'),
                    content_hash=page_data.get('content_hash')
                )
                session.add(page)
            
            generation = Generation(
                website_id=website.id,
                llms_txt_content=llms_content,
                version=1
            )
            session.add(generation)
            session.commit()
            session.refresh(generation)
            
            return jsonify({
                'id': generation.id,
                'website_id': website.id,
                'content': llms_content,
                'version': generation.version,
                'created_at': generation.created_at.isoformat()
            })
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Error generating llms.txt: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/monitor', methods=['POST'])
def register_monitoring():
    """Register a website for ongoing monitoring"""
    try:
        data = request.get_json()
        url = data.get('url')
        check_interval = data.get('check_interval', 3600)
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        session = get_db_session()
        try:
            website = session.query(Website).filter(Website.url == url).first()
            
            if not website:
                crawler = WebCrawler(url, max_depth=3, max_pages=100)
                pages = crawler.crawl()
                
                if not pages:
                    return jsonify({'error': 'No pages found on the website'}), 404
                
                generator = LLMsTxtGenerator()
                llms_content = generator.generate(pages)
                
                website = Website(
                    url=url,
                    status='completed',
                    monitoring_enabled=True,
                    check_interval=check_interval or 3600
                )
                session.add(website)
                session.commit()
                session.refresh(website)
                
                for page_data in pages:
                    page = Page(
                        website_id=website.id,
                        url=page_data['url'],
                        title=page_data.get('title'),
                        description=page_data.get('description'),
                        content_hash=page_data.get('content_hash')
                    )
                    session.add(page)
                
                generation = Generation(
                    website_id=website.id,
                    llms_txt_content=llms_content,
                    version=1
                )
                session.add(generation)
                session.commit()
            else:
                website.monitoring_enabled = True
                website.check_interval = check_interval
                session.commit()
            
            return jsonify({
                'id': website.id,
                'url': website.url,
                'monitoring_enabled': website.monitoring_enabled,
                'check_interval': website.check_interval,
                'last_checked': website.last_checked.isoformat() if website.last_checked else None
            })
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Error registering monitoring: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/monitor/<int:website_id>', methods=['DELETE'])
def stop_monitoring(website_id):
    """Stop monitoring a website"""
    try:
        session = get_db_session()
        try:
            website = session.query(Website).filter(Website.id == website_id).first()
            if not website:
                return jsonify({'error': 'Website not found'}), 404
            
            website.monitoring_enabled = False
            session.commit()
            
            return jsonify({'message': 'Monitoring stopped'})
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error stopping monitoring: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/status/<int:website_id>', methods=['GET'])
def get_status(website_id):
    """Get status and information for a website"""
    try:
        session = get_db_session()
        try:
            website = session.query(Website).filter(Website.id == website_id).first()
            if not website:
                return jsonify({'error': 'Website not found'}), 404
            
            latest_generation = session.query(Generation).filter(
                Generation.website_id == website_id
            ).order_by(Generation.version.desc()).first()
            
            return jsonify({
                'id': website.id,
                'url': website.url,
                'status': website.status,
                'monitoring_enabled': website.monitoring_enabled,
                'last_checked': website.last_checked.isoformat() if website.last_checked else None,
                'check_interval': website.check_interval,
                'pages_count': len(website.pages),
                'latest_version': latest_generation.version if latest_generation else None,
                'latest_created_at': latest_generation.created_at.isoformat() if latest_generation else None
            })
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<int:generation_id>', methods=['GET'])
def download_llms_txt(generation_id):
    """Download llms.txt file"""
    try:
        session = get_db_session()
        try:
            generation = session.query(Generation).filter(Generation.id == generation_id).first()
            if not generation:
                return jsonify({'error': 'Generation not found'}), 404
            
            website = generation.website
            filename = f"{website.url.replace('https://', '').replace('http://', '').replace('/', '_')}_llms.txt"
            
            return send_file(
                io.BytesIO(generation.llms_txt_content.encode('utf-8')),
                mimetype='text/plain',
                as_attachment=True,
                download_name=filename
            )
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error downloading llms.txt: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/monitored', methods=['GET'])
def get_monitored_websites():
    """Get all monitored websites"""
    try:
        session = get_db_session()
        try:
            websites = session.query(Website).filter(
                Website.monitoring_enabled == True
            ).all()
            
            result = []
            for website in websites:
                latest_gen = session.query(Generation).filter(
                    Generation.website_id == website.id
                ).order_by(Generation.version.desc()).first()
                
                result.append({
                    'id': website.id,
                    'url': website.url,
                    'status': website.status,
                    'last_checked': website.last_checked.isoformat() if website.last_checked else None,
                    'check_interval': website.check_interval,
                    'pages_count': len(website.pages),
                    'latest_version': latest_gen.version if latest_gen else None
                })
            
            return jsonify(result)
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error getting monitored websites: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/changes/<int:website_id>', methods=['GET'])
def get_changes(website_id):
    """Get change history for a website"""
    try:
        limit = request.args.get('limit', 50, type=int)
        session = get_db_session()
        try:
            website = session.query(Website).filter(Website.id == website_id).first()
            if not website:
                return jsonify({'error': 'Website not found'}), 404
            
            monitor = ChangeMonitor(session)
            changes = monitor.get_change_history(website_id, limit)
            
            result = [{
                'id': change.id,
                'change_type': change.change_type,
                'page_url': change.page_url,
                'detected_at': change.detected_at.isoformat(),
                'description': change.description
            } for change in changes]
            
            return jsonify(result)
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error getting changes: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'})

@app.route('/api/monitor/<int:website_id>/check', methods=['POST'])
def trigger_immediate_check(website_id):
    """Manually trigger an immediate check for a monitored website (bypasses interval)"""
    try:
        session = get_db_session()
        try:
            monitor = ChangeMonitor(session)
            changes_detected = monitor.check_website_immediately(website_id)
            
            website = session.query(Website).filter(Website.id == website_id).first()
            if not website:
                return jsonify({'error': 'Website not found'}), 404
            
            latest_gen = session.query(Generation).filter(
                Generation.website_id == website_id
            ).order_by(Generation.version.desc()).first()
            
            return jsonify({
                'website_id': website_id,
                'changes_detected': changes_detected,
                'latest_version': latest_gen.version if latest_gen else None,
                'last_checked': website.last_checked.isoformat() if website.last_checked else None,
                'message': 'Check completed' if not changes_detected else 'Changes detected and llms.txt updated'
            })
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error triggering immediate check: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/webhook/change', methods=['POST'])
def webhook_change_notification():
    """Webhook endpoint for websites to notify us of changes"""
    try:
        data = request.get_json()
        url = data.get('url')
        secret = data.get('secret')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        session = get_db_session()
        try:
            website = session.query(Website).filter(Website.url == url).first()
            if not website:
                return jsonify({'error': 'Website not found or not monitored'}), 404
            
            if not website.monitoring_enabled:
                return jsonify({'error': 'Website monitoring is not enabled'}), 400
            
            monitor = ChangeMonitor(session)
            changes_detected = monitor.check_website_immediately(website.id)
            
            return jsonify({
                'website_id': website.id,
                'url': website.url,
                'changes_detected': changes_detected,
                'message': 'Website checked and updated' if changes_detected else 'No changes detected'
            })
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('FLASK_PORT', 5001))
    app.run(debug=True, port=port)

