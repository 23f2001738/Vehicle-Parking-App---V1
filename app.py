from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
from models import db, ParkingLot, ParkingSpot, User, Reservation
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///parking.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)
db.init_app(app)

with app.app_context():
    db.create_all()
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(username='admin', password='admin123', role='admin')
        db.session.add(admin)
        db.session.commit()
        print("Default admin user created: username='admin', password='admin123'")
    else:
        print(f"Admin user already exists: username='{admin.username}', role='{admin.role}'")

def get_current_user():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        print(f"Current user: {user.username if user else 'None'}")
        return user
    print("No user_id in session")
    return None

@app.route('/')
def index():
    user = get_current_user()
    if user:
        if user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('user_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        print(f"Login attempt: username='{username}', password='{password}'")
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            print(f"User found: username='{user.username}', role='{user.role}'")
            session['user_id'] = user.id
            session.permanent = True
            if user.role == 'admin':
                print("Redirecting to admin dashboard")
                return redirect(url_for('admin_dashboard'))
            else:
                print("Redirecting to user dashboard")
                return redirect(url_for('user_dashboard'))
        else:
            print("User not found or credentials incorrect")
            flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('register'))
        new_user = User(username=username, password=password, role='user')
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/admin/dashboard')
def admin_dashboard():
    user = get_current_user()
    if not user or user.role != 'admin':
        print(f"Access denied: user={user.username if user else 'None'}, role={user.role if user else 'None'}")
        flash('Admin access required.', 'danger')
        return redirect(url_for('login'))
    lots = ParkingLot.query.all()
    spots = ParkingSpot.query.all()
    active_reservations = Reservation.query.filter_by(leaving_timestamp=None).all()
    reservation_dict = {res.spot_id: res for res in active_reservations}
    lot_dict = {lot.id: lot for lot in lots}
    users = User.query.all()
    user_dict = {user.id: user for user in users}
    spots_with_details = []
    for spot in spots:
        reservation = reservation_dict.get(spot.id)
        user = user_dict.get(reservation.user_id) if reservation else None
        spots_with_details.append({
            'spot': spot,
            'lot': lot_dict.get(spot.lot_id),
            'reservation': reservation,
            'user': user
        })
    total_lots = len(lots)
    total_spots = len(spots)
    occupied_spots = len([spot for spot in spots if spot.status == 'O'])
    available_spots = total_spots - occupied_spots
    total_reservations = len(active_reservations)
    print(f"Admin Dashboard Data - Total Lots: {total_lots}, Total Spots: {total_spots}, Occupied: {occupied_spots}, Available: {available_spots}, Total Reservations: {total_reservations}")
    return render_template('admin_dashboard.html', lots=lots, spots_with_details=spots_with_details, total_lots=total_lots, total_spots=total_spots, occupied_spots=occupied_spots, available_spots=available_spots, total_reservations=total_reservations)

@app.route('/admin/create_lot', methods=['POST'])
def create_lot():
    user = get_current_user()
    if not user or user.role != 'admin':
        return redirect(url_for('login'))
    name = request.form['name']
    price = float(request.form['price'])
    address = request.form['address']
    pincode = request.form['pincode']
    max_spots = int(request.form['max_spots'])

    lot = ParkingLot(
        prime_location_name=name,
        price=price,
        address=address,
        pin_code=pincode,
        maximum_number_of_spots=max_spots
    )
    db.session.add(lot)
    db.session.commit()

    for i in range(max_spots):
        spot = ParkingSpot(lot_id=lot.id, status='A')
        db.session.add(spot)
    db.session.commit()

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit_lot/<int:lot_id>', methods=['GET', 'POST'])
def edit_lot(lot_id):
    user = get_current_user()
    if not user or user.role != 'admin':
        return redirect(url_for('login'))
    lot = ParkingLot.query.get_or_404(lot_id)
    if request.method == 'POST':
        lot.prime_location_name = request.form['name']
        lot.price = float(request.form['price'])
        lot.address = request.form['address']
        lot.pin_code = request.form['pincode']
        lot.maximum_number_of_spots = int(request.form['max_spots'])
        current_spots = ParkingSpot.query.filter_by(lot_id=lot.id).count()
        if lot.maximum_number_of_spots > current_spots:
            for i in range(lot.maximum_number_of_spots - current_spots):
                spot = ParkingSpot(lot_id=lot.id, status='A')
                db.session.add(spot)
        elif lot.maximum_number_of_spots < current_spots:
            spots_to_remove = ParkingSpot.query.filter_by(lot_id=lot.id, status='A').limit(current_spots - lot.maximum_number_of_spots).all()
            for spot in spots_to_remove:
                db.session.delete(spot)
        db.session.commit()
        flash('Parking lot updated successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('edit_lot.html', lot=lot)

@app.route('/admin/delete_lot/<int:lot_id>', methods=['POST'])
def delete_lot(lot_id):
    user = get_current_user()
    if not user or user.role != 'admin':
        return redirect(url_for('login'))
    lot = ParkingLot.query.get_or_404(lot_id)
    spots = ParkingSpot.query.filter_by(lot_id=lot.id).all()
    if any(spot.status == 'O' for spot in spots):
        flash('Cannot delete a lot with occupied spots.', 'danger')
        return redirect(url_for('admin_dashboard'))
    for spot in spots:
        db.session.delete(spot)
    db.session.delete(lot)
    db.session.commit()
    flash('Parking lot deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/view_spot/<int:spot_id>')
def view_spot(spot_id):
    user = get_current_user()
    if not user or user.role != 'admin':
        return redirect(url_for('login'))
    spot = ParkingSpot.query.get_or_404(spot_id)
    return render_template('view_spot.html', spot=spot)

@app.route('/admin/spot_details/<int:spot_id>')
def spot_details(spot_id):
    user = get_current_user()
    if not user or user.role != 'admin':
        return redirect(url_for('login'))
    spot = ParkingSpot.query.get_or_404(spot_id)
    reservation = Reservation.query.filter_by(spot_id=spot_id).first()
    if not reservation:
        return redirect(url_for('view_spot', spot_id=spot_id))
    return render_template('spot_details.html', spot=spot, reservation=reservation)

@app.route('/admin/delete_spot/<int:spot_id>', methods=['POST'])
def delete_spot(spot_id):
    user = get_current_user()
    if not user or user.role != 'admin':
        return redirect(url_for('login'))
    spot = ParkingSpot.query.get_or_404(spot_id)
    if spot.status == 'O':
        return "Cannot delete an occupied spot", 400
    db.session.delete(spot)
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/search', methods=['GET'])
def search_lots():
    user = get_current_user()
    if not user or user.role != 'admin':
        flash('Admin access required.', 'danger')
        return redirect(url_for('login'))
    query = request.args.get('query', '')
    lots = ParkingLot.query.filter(ParkingLot.prime_location_name.ilike(f'%{query}%')).all()
    spots = ParkingSpot.query.join(ParkingLot).filter(ParkingLot.prime_location_name.ilike(f'%{query}%')).all()
    active_reservations = Reservation.query.filter_by(leaving_timestamp=None).all()
    reservation_dict = {res.spot_id: res for res in active_reservations}
    lot_dict = {lot.id: lot for lot in lots}
    users = User.query.all()
    user_dict = {user.id: user for user in users}
    spots_with_details = []
    for spot in spots:
        reservation = reservation_dict.get(spot.id)
        user = user_dict.get(reservation.user_id) if reservation else None
        spots_with_details.append({
            'spot': spot,
            'lot': lot_dict.get(spot.lot_id),
            'reservation': reservation,
            'user': user
        })
    total_lots = len(lots)
    total_spots = len(spots)
    occupied_spots = len([spot for spot in spots if spot.status == 'O'])
    available_spots = total_spots - occupied_spots
    total_reservations = len(active_reservations)
    return render_template('admin_dashboard.html', lots=lots, spots_with_details=spots_with_details, total_lots=total_lots, total_spots=total_spots, occupied_spots=occupied_spots, available_spots=available_spots, total_reservations=total_reservations)

@app.route('/user/dashboard')
def user_dashboard():
    user = get_current_user()
    if not user or user.role != 'user':
        flash('User access required.', 'danger')
        return redirect(url_for('login'))
    lots = ParkingLot.query.all()
    spots = ParkingSpot.query.filter_by(status='A').all()
    history = Reservation.query.filter_by(user_id=user.id).order_by(Reservation.parking_timestamp.desc()).all()
    history_with_spots = []
    for res in history:
        spot = ParkingSpot.query.get(res.spot_id)
        history_with_spots.append({
            'reservation': res,
            'lot_id': spot.lot_id if spot else 'N/A'
        })
    total_reservations = len(history)
    active_reservations = len([res for res in history if res.leaving_timestamp is None])
    reservation = Reservation.query.filter_by(user_id=user.id, leaving_timestamp=None).first()
    reserved_spot = None
    reserved_lot = None
    if reservation:
        reserved_spot = ParkingSpot.query.get(reservation.spot_id)
        reserved_lot = ParkingLot.query.get(reserved_spot.lot_id)
    return render_template('user_dashboard.html', user=user, lots=lots, spots=spots, reservation=reservation, reserved_spot=reserved_spot, reserved_lot=reserved_lot, history=history_with_spots, total_reservations=total_reservations, active_reservations=active_reservations)

@app.route('/user/reserve_spot', methods=['POST'])
def reserve_spot():
    user = get_current_user()
    if not user or user.role != 'user':
        flash('User access required.', 'danger')
        return redirect(url_for('login'))
    
    existing_reservation = Reservation.query.filter_by(user_id=user.id, leaving_timestamp=None).first()
    if existing_reservation:
        flash('You already have an active reservation. Please release it before reserving another spot.', 'danger')
        return redirect(url_for('user_dashboard'))
    
    lot_id = int(request.form['lot_id'])
    vehicle_number = request.form['vehicle_number']
    spot = ParkingSpot.query.filter_by(lot_id=lot_id, status='A').first()
    if not spot:
        flash('No available spots in this parking lot.', 'danger')
        return redirect(url_for('user_dashboard'))
    
    spot.status = 'O'
    reservation = Reservation(
        spot_id=spot.id,
        user_id=user.id,
        vehicle_number=vehicle_number,
        parking_timestamp=datetime.utcnow()
    )
    db.session.add(reservation)
    db.session.commit()
    flash('Spot reserved successfully!', 'success')
    return redirect(url_for('user_dashboard'))

@app.route('/user/release_spot/<int:reservation_id>', methods=['POST'])
def release_spot(reservation_id):
    user = get_current_user()
    if not user or user.role != 'user':
        flash('User access required.', 'danger')
        return redirect(url_for('login'))
    
    reservation = Reservation.query.get_or_404(reservation_id)
    if reservation.user_id != user.id:
        flash('You are not authorized to release this spot.', 'danger')
        return redirect(url_for('user_dashboard'))
    
    reservation.leaving_timestamp = datetime.utcnow()
    spot = ParkingSpot.query.get(reservation.spot_id)
    lot = ParkingLot.query.get(spot.lot_id)
    time_parked = (reservation.leaving_timestamp - reservation.parking_timestamp).total_seconds() / 3600
    reservation.parking_cost = lot.price * time_parked
    spot.status = 'A'
    db.session.commit()
    flash(f'Spot released successfully! Parking cost: ${reservation.parking_cost:.2f}', 'success')
    return redirect(url_for('user_dashboard'))

@app.route('/user/search', methods=['GET'])
def user_search_lots():
    user = get_current_user()
    if not user or user.role != 'user':
        flash('User access required.', 'danger')
        return redirect(url_for('login'))
    query = request.args.get('query', '')
    lots = ParkingLot.query.filter(ParkingLot.prime_location_name.ilike(f'%{query}%')).all()
    spots = ParkingSpot.query.filter_by(status='A').join(ParkingLot).filter(ParkingLot.prime_location_name.ilike(f'%{query}%')).all()
    history = Reservation.query.filter_by(user_id=user.id).order_by(Reservation.parking_timestamp.desc()).all()
    history_with_spots = []
    for res in history:
        spot = ParkingSpot.query.get(res.spot_id)
        history_with_spots.append({
            'reservation': res,
            'lot_id': spot.lot_id if spot else 'N/A'
        })
    total_reservations = len(history)
    active_reservations = len([res for res in history if res.leaving_timestamp is None])
    reservation = Reservation.query.filter_by(user_id=user.id, leaving_timestamp=None).first()
    reserved_spot = None
    reserved_lot = None
    if reservation:
        reserved_spot = ParkingSpot.query.get(reservation.spot_id)
        reserved_lot = ParkingLot.query.get(reserved_spot.lot_id)
    return render_template('user_dashboard.html', user=user, lots=lots, spots=spots, reservation=reservation, reserved_spot=reserved_spot, reserved_lot=reserved_lot, history=history_with_spots, total_reservations=total_reservations, active_reservations=active_reservations)

@app.route('/api/spots', methods=['GET'])
def get_spots():
    spots = ParkingSpot.query.all()
    return jsonify([{
        'id': spot.id,
        'lot_id': spot.lot_id,
        'status': spot.status
    } for spot in spots])

@app.route('/debug_session')
def debug_session():
    return jsonify(dict(session))

@app.route('/debug_schema')
def debug_schema():
    conn = sqlite3.connect('parking.db')
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(reservation);")
    columns = cursor.fetchall()
    conn.close()
    return jsonify(columns)

@app.context_processor
def utility_processor():
    return dict(get_current_user=get_current_user)

if __name__ == '__main__':
    app.run(debug=True)