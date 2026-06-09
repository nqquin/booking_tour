from flask import Blueprint, request, jsonify
from app.extensions import db, supabase
from app.models.user import User
from app.models.chat import Message, AIChatHistory
from app.models.tour import Tour
from app.models.order import Order
from app.models.review import Review
from app.models.log import SearchLog, TourViewLog
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, desc
from datetime import datetime
from app.log_service import log_user_action
import requests
import os
import re
import json
from app.services.recommendation_service import get_popular_tours

chat_bp = Blueprint('chat', __name__)
OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3"

def detect_intent(message):
    msg = message.lower().strip()
    
    intent = {
        "beach": any(kw in msg for kw in ["biển", "đảo", "nha trang", "phú quốc", "quy nhơn", "hòn", "vịnh", "nam du"]),
        "mountain": any(kw in msg for kw in ["núi", "đà lạt", "sapa", "tây bắc", "cao nguyên", "mộc châu", "măng đen"]),
        "popular": any(kw in msg for kw in ["bán chạy", "nhiều người mua", "hot", "phổ biến", "được chuộng"]),
        "top_rated": any(kw in msg for kw in ["đánh giá cao", "tốt nhất", "nhiều sao", "chất lượng", "review tốt"]),
        "healing_solo": any(kw in msg for kw in ["buồn", "thất tình", "chán", "chữa lành", "giải khuây", "xả stress", "1 mình", "một mình", "yên bình", "tĩnh lặng", "áp lực"]),
        "group_fun": any(kw in msg for kw in ["vui", "nhóm", "đám bạn", "bạn bè", "đông người", "quẩy", "team building", "sôi động", "công ty"]),
        "dating": any(kw in msg for kw in ["hẹn hò", "người yêu", "bạn gái", "bạn trai", "cặp đôi", "lãng mạn", "trăng mật", "tuần trăng mật", "hâm nóng"]),
        "family": any(kw in msg for kw in ["gia đình", "bố mẹ", "ông bà", "người già", "lớn tuổi", "trẻ con", "trẻ em", "em bé", "nghỉ dưỡng"]),
        "duration": None, # Số ngày đi
        "budget_max": None # Ngân sách
    }
    
    #Lấy ý định: Số ngày đi (Ví dụ: "tour 3 ngày", "đi 4 ngày")
    duration_match = re.search(r'(\d+)\s*ngày', msg)
    if duration_match:
        intent["duration"] = int(duration_match.group(1))

    #lấy ý định: Ngân sách (Ví dụ: "giá 5 triệu", "5tr")
    budget_match = re.search(r'(\d+)\s*(triệu|tr|đồng|d|vnđ)?', msg)
    if budget_match:
        num = int(budget_match.group(1))
        unit = budget_match.group(2) or ""
        if "triệu" in unit or "tr" in unit:
            intent["budget_max"] = num * 1_000_000
        else:
            intent["budget_max"] = num if num > 1000000 else num * 1_000_000 

    return intent

def ensure_minimum_tours(tours, min_count=4):
    if len(tours) >= min_count:
        return tours
    popular = get_popular_tours(min_count)
    existing_ids = {t.id for t in tours}
    for p in popular:
        if p.id not in existing_ids:
            tours.append(p)
        if len(tours) >= min_count:
            break
    return tours



@chat_bp.route('/partners', methods=['GET'])
@jwt_required()
def get_chat_partners():
    current_user_id = str(get_jwt_identity())
    try:
        response = supabase.table("messages")\
            .select("sender_id, receiver_id")\
            .or_(f"sender_id.eq.{current_user_id},receiver_id.eq.{current_user_id}")\
            .execute()
        messages = response.data or []

        partner_ids = {msg['receiver_id'] if msg['sender_id'] == current_user_id else msg['sender_id'] for msg in messages}
        
        partners = []
        for pid in partner_ids:
            pid_str = str(pid)
            if len(pid_str) < 30: 
                continue
                
            user = User.query.filter_by(id=pid_str).first() 
                
            if user:
                user_msgs = [m for m in messages if 
                             (str(m['sender_id']) == current_user_id and str(m['receiver_id']) == pid_str) or 
                             (str(m['sender_id']) == pid_str and str(m['receiver_id']) == current_user_id)]
                
                user_msgs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)    
                last_msg = user_msgs[0] if user_msgs else None
                role_display = "Hướng dẫn viên" if user.role.value == 'guide' else "Khách hàng"

                partners.append({
                    "id": str(user.id),
                    "name": user.full_name,
                    "role": role_display,
                    "lastMessage": last_msg.get('content', "") if last_msg else ""
                })
        return jsonify(partners), 200
    except Exception as e:
        print("Lỗi get partners:", str(e))
        return jsonify({"error": str(e)}), 500


@chat_bp.route('/ai', methods=['POST'])
@jwt_required()
def chat_with_ai():
    from sqlalchemy import text
    try:
        db.session.execute(text("SELECT user_id FROM ai_chat_history LIMIT 1"))
    except Exception:
        db.session.rollback()
        db.session.execute(text("DROP TABLE IF EXISTS ai_chat_history CASCADE;"))
        db.session.commit()
        db.create_all()

    data = request.get_json()
    user_message = data.get('message')
    user_id = str(get_jwt_identity()) 
    session_id = data.get('session_id', 'default')
    
    if not user_message:
        return jsonify({"reply": "Bạn chưa nhập tin nhắn."}), 400

    recent_keywords = "chưa có"
    recent_views = "chưa xem"
    recent_orders = "chưa đặt tour nào"

    try:
        searches = SearchLog.query.filter_by(user_id=user_id).order_by(SearchLog.searched_at.desc()).limit(5).all() 
        log_user_action("chat_ai", details=f"Chat với AI: {user_message[:100]}...")
        if searches:
            k_list = [s.keyword for s in searches if s.keyword]
            if k_list: recent_keywords = ", ".join(k_list)

        views = TourViewLog.query.filter_by(user_id=user_id).order_by(TourViewLog.viewed_at.desc()).limit(4).all()
        recent_views_list = [Tour.query.get(v.tour_id).name for v in views if Tour.query.get(v.tour_id)]
        if recent_views_list: recent_views = ", ".join(recent_views_list)

        orders = Order.query.filter_by(user_id=user_id).order_by(Order.booking_date.desc()).limit(3).all()
        recent_orders_list = [Tour.query.get(o.tour_id).name for o in orders if Tour.query.get(o.tour_id)]
        if recent_orders_list: recent_orders = ", ".join(recent_orders_list)
    except Exception as e:
        print(f"Context Error: {e}")

    context_extra = f"Khách tìm kiếm: {recent_keywords}\nKhách đã xem: {recent_views}\nKhách đã đặt: {recent_orders}"

    intent = detect_intent(user_message)
    query = Tour.query.filter(Tour.status == 'approved', Tour.start_date >= datetime.utcnow())

    if intent["beach"]: 
        query = query.filter(Tour.itinerary.ilike("%biển%") | Tour.description.ilike("%biển%"))
    
    if intent["mountain"]: 
        query = query.filter(Tour.itinerary.ilike("%núi%") | Tour.description.ilike("%núi%"))
    
    if intent["healing_solo"]:
        query = query.filter(Tour.description.ilike("%chữa lành%") | Tour.description.ilike("%một mình%") | Tour.description.ilike("%tĩnh lặng%") | Tour.description.ilike("%buồn%") | Tour.description.ilike("%stress%"))
    
    if intent["group_fun"]:
        query = query.filter(Tour.description.ilike("%nhóm%") | Tour.description.ilike("%vui%") | Tour.description.ilike("%quẩy%") | Tour.description.ilike("%team building%"))
    
    if intent["dating"]:
        query = query.filter(Tour.description.ilike("%hẹn hò%") | Tour.description.ilike("%cặp đôi%") | Tour.description.ilike("%lãng mạn%"))
        
    if intent["family"]:
        query = query.filter(Tour.description.ilike("%gia đình%") | Tour.description.ilike("%trẻ%") | Tour.description.ilike("%người lớn%"))

    if intent["budget_max"]: 
        query = query.filter(Tour.price <= intent["budget_max"])

    # Lọc theo số ngày đi
    if intent["duration"]:
        try:
            query = query.filter(func.extract('day', Tour.end_date - Tour.start_date) >= (intent["duration"] - 1))
            query = query.filter(func.extract('day', Tour.end_date - Tour.start_date) <= (intent["duration"] + 1))
        except Exception:
            pass

    # Sắp xếp theo Tour Bán Chạy Nhất 
    if intent["popular"]:
        query = query.outerjoin(Order, Tour.id == Order.tour_id)\
                     .filter(Order.status.in_(['paid', 'completed', 'success']))\
                     .group_by(Tour.id)\
                     .order_by(desc(func.count(Order.id)))

    # Sắp xếp theo Đánh Giá Cao Nhất 
    elif intent["top_rated"]:
        query = query.outerjoin(Review, Tour.id == Review.tour_id)\
                     .group_by(Tour.id)\
                     .order_by(desc(func.avg(Review.rating)))

    filtered_tours = query.limit(6).all()
    final_tours = ensure_minimum_tours(filtered_tours, min_count=4)
    tour_context = "\n".join([f"- ID {t.id}: {t.name} ({t.price:,} VNĐ) - Bắt đầu: {t.start_date.strftime('%d/%m/%Y') if t.start_date else 'N/A'}" for t in final_tours])

    system_prompt = f"""
    Bạn là **Trợ lý du lịch chuyên nghiệp** của công ty tour Việt Nam, tên là "DuLichAI".
    Phong cách: Thân thiện, nhiệt tình, ngắn gọn, dùng tiếng Việt tự nhiên.
    Thông tin khách hàng: {context_extra}
    Danh sách tour: {tour_context}
    YÊU CẦU: Trả về duy nhất JSON: {{"reply": "nội dung", "tour_ids": [id1, id2]}}
    """

    payload = {
        "model": MODEL_NAME,
        "prompt": f"{system_prompt}\n\nKhách hàng hỏi: {user_message}",
        "format": "json",
        "stream": False,
        "temperature": 0.7
    }

    reply = "Chào anh/chị! Dưới đây là những tour em tìm được theo đúng yêu cầu của anh/chị ạ:"
    suggested_ids = []

    try:
        resp = requests.post(OLLAMA_API_URL, json=payload, timeout=60)
        if resp.status_code == 200:
            ai_text = resp.json().get('response', '').strip()
            for line in ai_text.split('\n'):
                line = line.strip()
                if '{' in line and '}' in line:
                    try:
                        start = line.find('{')
                        end = line.rfind('}')
                        parsed = json.loads(line[start:end+1])
                        reply = parsed.get('reply', reply)
                        raw_ids = parsed.get('tour_ids', [])
                        suggested_ids = [int(x) for x in raw_ids if str(x).isdigit()]
                        break
                    except: continue
    except Exception as e:
        print(f"Lỗi gọi Ollama: {e}")

    if not suggested_ids and final_tours:
        suggested_ids = [t.id for t in final_tours[:3]]

    suggested_tours = []
    if suggested_ids:
        tours_db = Tour.query.filter(Tour.id.in_(suggested_ids)).all()
        suggested_tours = [{"id": t.id, "name": t.name, "price": t.price, "image": t.image} for t in tours_db]

    try:
        db.session.add(AIChatHistory(user_id=user_id, session_id=session_id, role='user', content=user_message))
        db.session.add(AIChatHistory(user_id=user_id, session_id=session_id, role='assistant', content=reply, tours=suggested_tours))
        db.session.commit()
    except Exception as e:
        print(f"Lỗi lưu DB: {e}")
        db.session.rollback()

    return jsonify({"reply": reply, "suggested_tours": suggested_tours}), 200

@chat_bp.route('/ai/history', methods=['GET'])
@jwt_required()
def get_ai_history():
    user_id = str(get_jwt_identity())
    session_id = request.args.get('session_id')
    try:
        if session_id:
            history = AIChatHistory.query.filter_by(user_id=user_id, session_id=session_id).order_by(AIChatHistory.created_at.asc()).all()
        else:
            history = AIChatHistory.query.filter_by(user_id=user_id).order_by(AIChatHistory.created_at.asc()).limit(20).all()
        
        return jsonify([{
            "sender_id": "AI" if m.role == 'assistant' else str(m.user_id),
            "content": m.content,
            "tours": m.tours,
            "timestamp": m.created_at.isoformat() if m.created_at else ""
        } for m in history]), 200
    except Exception:
        return jsonify([]), 200

@chat_bp.route('/messages/<string:partner_id>', methods=['GET'])
@jwt_required()
def get_full_chat_history(partner_id):
    current_user_id = str(get_jwt_identity())
    try:
        cond1 = f"and(sender_id.eq.{current_user_id},receiver_id.eq.{partner_id})"
        cond2 = f"and(sender_id.eq.{partner_id},receiver_id.eq.{current_user_id})"
        response = supabase.table("messages").select("*").or_(f"{cond1},{cond2}").order("timestamp", desc=False).execute()
        messages = response.data or []
        supabase.table("messages").update({"is_read": True}).eq("sender_id", partner_id).eq("receiver_id", current_user_id).execute()

        return jsonify([{
            "id": msg.get('id'),
            "sender_id": str(msg.get('sender_id')),
            "receiver_id": str(msg.get('receiver_id')),
            "content": msg.get('content', ''),
            "timestamp": msg.get('created_at') or msg.get('timestamp') or ""
        } for msg in messages]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@chat_bp.route('/send', methods=['POST'])
@jwt_required()
def send_message():
    data = request.get_json()
    sender_id = str(get_jwt_identity())
    receiver_id = str(data.get('receiver_id'))
    content = data.get('content')
    if not content: return jsonify({'error': 'Nội dung trống'}), 400

    try:
        res = supabase.table('messages').insert({
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "content": content,
            "is_read": False,
            "timestamp": datetime.utcnow().isoformat()
        }).execute()
        return jsonify({'status': 'success', 'data': res.data[0]}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500