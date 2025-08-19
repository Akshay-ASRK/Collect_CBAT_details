from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pandas as pd
import numpy as np
import os
import tempfile
from werkzeug.security import check_password_hash, generate_password_hash

BASEDIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASEDIR, 'instance', 'cbat_reports.db')
os.makedirs(os.path.join(BASEDIR, 'instance'), exist_ok=True)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-herehcvbmnvjcftxhgcvbjfgxzsrdhtfdgfjvbuydgxyerdtsdhfg'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database Model
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    roll_no = db.Column(db.String(15), unique=True, nullable=False)
    is_reexam = db.Column(db.Boolean, nullable=False)
    cbt2_marks = db.Column(db.Float, nullable=False)
    rrb_zone = db.Column(db.String(50), nullable=False)
    exam_date = db.Column(db.Date, nullable=False)
    shift = db.Column(db.String(10), nullable=False)
    
    # Battery Test Attempts
    memory_attempts = db.Column(db.Integer, nullable=False)
    memory_accuracy = db.Column(db.Float, nullable=False)
    directions_attempts = db.Column(db.Integer, nullable=False)
    directions_accuracy = db.Column(db.Float, nullable=False)
    depth_attempts = db.Column(db.Integer, nullable=False)
    depth_accuracy = db.Column(db.Float, nullable=False)
    concentration_attempts = db.Column(db.Integer, nullable=False)
    concentration_accuracy = db.Column(db.Float, nullable=False)
    perceptual_attempts = db.Column(db.Integer, nullable=False)
    perceptual_accuracy = db.Column(db.Float, nullable=False)
    
    # Calculated Scores
    memory_raw_score = db.Column(db.Float, nullable=True)
    directions_raw_score = db.Column(db.Float, nullable=True)
    depth_raw_score = db.Column(db.Float, nullable=True)
    concentration_raw_score = db.Column(db.Float, nullable=True)
    perceptual_raw_score = db.Column(db.Float, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Admin password (in production, use environment variables)
ADMIN_PASSWORD = generate_password_hash("admin123$@$%^%$##$%^*&^@@$*dvbdfbfsgbndgcJIHKGHJHVBhjbk,.jkvs")

def calculate_raw_scores(student):
    """Calculate raw scores based on attempts and accuracy"""
    student.memory_raw_score = int((student.memory_attempts * student.memory_accuracy) / 100 )
    student.directions_raw_score = int((student.directions_attempts * student.directions_accuracy) / 100 )
    student.depth_raw_score = int((student.depth_attempts * student.depth_accuracy) / 100 )
    student.concentration_raw_score = int((student.concentration_attempts * student.concentration_accuracy) / 100 )
    student.perceptual_raw_score = int((student.perceptual_attempts * student.perceptual_accuracy) / 100 )

def calculate_t_scores_and_overall(students, target_student):
    """Calculate T-scores and overall score for a student"""
    
    # Extract raw scores for all students
    memory_scores = [s.memory_raw_score for s in students]
    directions_scores = [s.directions_raw_score for s in students]
    depth_scores = [s.depth_raw_score for s in students]
    concentration_scores = [s.concentration_raw_score for s in students]
    perceptual_scores = [s.perceptual_raw_score for s in students]
    
    # Calculate means and standard deviations
    battery_stats = {
        'memory': {'mean': np.mean(memory_scores), 'std': np.std(memory_scores, ddof=0) if len(memory_scores) > 1 else 1},
        'directions': {'mean': np.mean(directions_scores), 'std': np.std(directions_scores, ddof=0) if len(directions_scores) > 1 else 1},
        'depth': {'mean': np.mean(depth_scores), 'std': np.std(depth_scores, ddof=0) if len(depth_scores) > 1 else 1},
        'concentration': {'mean': np.mean(concentration_scores), 'std': np.std(concentration_scores, ddof=0) if len(concentration_scores) > 1 else 1},
        'perceptual': {'mean': np.mean(perceptual_scores), 'std': np.std(perceptual_scores, ddof=0) if len(perceptual_scores) > 1 else 1}
    }
    
    # Calculate T-scores for target student
    # T = 50 + 10 * (X - Mean) / SD
    t_scores = {}
    t_scores['memory'] = 50 + 10 * (target_student.memory_raw_score - battery_stats['memory']['mean']) / battery_stats['memory']['std']
    t_scores['directions'] = 50 + 10 * (target_student.directions_raw_score - battery_stats['directions']['mean']) / battery_stats['directions']['std']
    t_scores['depth'] = 50 + 10 * (target_student.depth_raw_score - battery_stats['depth']['mean']) / battery_stats['depth']['std']
    t_scores['concentration'] = 50 + 10 * (target_student.concentration_raw_score - battery_stats['concentration']['mean']) / battery_stats['concentration']['std']
    t_scores['perceptual'] = 50 + 10 * (target_student.perceptual_raw_score - battery_stats['perceptual']['mean']) / battery_stats['perceptual']['std']
    
    # Calculate Overall Score
    total_t_score = sum(t_scores.values())
    overall_score = (total_t_score * 30) / 400
    
    return t_scores, overall_score, battery_stats

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/check_roll_no', methods=['POST'])
def check_roll_no():
    data = request.json
    roll_no = data.get('roll_no')
    
    student = Student.query.filter_by(roll_no=roll_no).first()
    if student:
        return jsonify({'exists': True, 'student_data': {
            'roll_no': student.roll_no,
            'is_reexam': student.is_reexam,
            'rrb_zone': student.rrb_zone,
            'exam_date': student.exam_date.strftime('%Y-%m-%d'),
            'shift': student.shift
        }})
    else:
        return jsonify({'exists': False})

@app.route('/get_reports', methods=['POST'])
def get_reports():
    data = request.json
    roll_no = data.get('roll_no')
    
    student = Student.query.filter_by(roll_no=roll_no).first()
    if not student:
        return jsonify({'error': 'Student not found'}), 404
    
    # Calculate raw scores if not already calculated
    if student.memory_raw_score is None:
        calculate_raw_scores(student)
        db.session.commit()
    
    # Get students for comparison based on zone and shift
    zone_shift_students = Student.query.filter_by(
        rrb_zone=student.rrb_zone, 
        shift=student.shift
    ).all()
    
    # Calculate raw scores for all students if needed
    for s in zone_shift_students:
        if s.memory_raw_score is None:
            calculate_raw_scores(s)
    db.session.commit()
    
    reports = {}
    
    if student.is_reexam:
        # Report 1: All Re-Exam Candidates
        reexam_students = [s for s in zone_shift_students if s.is_reexam]
        t_scores_reexam, overall_reexam, stats_reexam = calculate_t_scores_and_overall(reexam_students, student)
        
        # Report 2: All Candidates (Re-Exam + Non Re-Exam)
        t_scores_all, overall_all, stats_all = calculate_t_scores_and_overall(zone_shift_students, student)
        
        reports = {
            'reexam_only': {
                't_scores': t_scores_reexam,
                'overall_score': round(overall_reexam, 2),
                'battery_stats': stats_reexam,
                'comparison_group': f'Re-Exam Candidates in {student.rrb_zone} - Shift {student.shift}'
            },
            'all_candidates': {
                't_scores': t_scores_all,
                'overall_score': round(overall_all, 2),
                'battery_stats': stats_all,
                'comparison_group': f'All Candidates in {student.rrb_zone} - Shift {student.shift}'
            }
        }
    else:
        # Report 1: All Non Re-Exam Candidates
        non_reexam_students = [s for s in zone_shift_students if not s.is_reexam]
        t_scores_non_reexam, overall_non_reexam, stats_non_reexam = calculate_t_scores_and_overall(non_reexam_students, student)
        
        # Report 2: All Candidates (Re-Exam + Non Re-Exam)
        t_scores_all, overall_all, stats_all = calculate_t_scores_and_overall(zone_shift_students, student)
        
        reports = {
            'non_reexam_only': {
                't_scores': t_scores_non_reexam,
                'overall_score': round(overall_non_reexam, 2),
                'battery_stats': stats_non_reexam,
                'comparison_group': f'Non Re-Exam Candidates in {student.rrb_zone} - Shift {student.shift}'
            },
            'all_candidates': {
                't_scores': t_scores_all,
                'overall_score': round(overall_all, 2),
                'battery_stats': stats_all,
                'comparison_group': f'All Candidates in {student.rrb_zone} - Shift {student.shift}'
            }
        }
    
    return jsonify({
        'student_info': {
            'roll_no': student.roll_no,
            'exam_date': student.exam_date.strftime('%d-%m-%Y'),
            'shift': student.shift.title(),
            'rrb_zone': student.rrb_zone,
            'cbt2_marks': student.cbt2_marks,
            'is_reexam': student.is_reexam
        },
        'reports': reports
    })

@app.route('/submit_form', methods=['POST'])
def submit_form():
    data = request.json
    
    try:
        # Check if roll number already exists
        existing_student = Student.query.filter_by(roll_no=data['roll_no']).first()
        
        if existing_student and not data.get('confirm_update', False):
            return jsonify({'exists': True, 'message': 'Roll number already exists'})
        
        # Create or update student data
        if existing_student:
            student = existing_student
        else:
            student = Student()
        
        # Update student data
        student.roll_no = data['roll_no']
        student.is_reexam = data['is_reexam']
        student.cbt2_marks = float(data['cbt2_marks'])
        student.rrb_zone = data['rrb_zone']
        student.exam_date = datetime.strptime(data['exam_date'], '%Y-%m-%d').date()
        student.shift = data['shift']
        
        student.memory_attempts = int(data['memory_attempts'])
        student.memory_accuracy = float(data['memory_accuracy'])
        student.directions_attempts = int(data['directions_attempts'])
        student.directions_accuracy = float(data['directions_accuracy'])
        student.depth_attempts = int(data['depth_attempts'])
        student.depth_accuracy = float(data['depth_accuracy'])
        student.concentration_attempts = int(data['concentration_attempts'])
        student.concentration_accuracy = float(data['concentration_accuracy'])
        student.perceptual_attempts = int(data['perceptual_attempts'])
        student.perceptual_accuracy = float(data['perceptual_accuracy'])
        
        # Calculate raw scores
        calculate_raw_scores(student)
        
        if not existing_student:
            db.session.add(student)
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Form submitted successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin')
def admin_login():
    return render_template('admin.html')

@app.route('/admin/verify', methods=['POST'])
def verify_admin():
    data = request.json
    password = data.get('password')
    
    if check_password_hash(ADMIN_PASSWORD, password):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'message': 'Invalid password'})

@app.route('/admin/download_csv', methods=['POST'])
def download_csv():
    data = request.json
    password = data.get('password')
    
    if not check_password_hash(ADMIN_PASSWORD, password):
        return jsonify({'error': 'Invalid password'}), 401
    
    try:
        # Get all students
        all_students = Student.query.all()
        
        # Calculate raw scores for all students if needed
        for student in all_students:
            if student.memory_raw_score is None:
                calculate_raw_scores(student)
        db.session.commit()
        
        # Prepare CSV data
        csv_data = []
        
        # Group students by zone and shift for T-score calculations
        zone_shift_groups = {}
        for student in all_students:
            key = f"{student.rrb_zone}_{student.shift}"
            if key not in zone_shift_groups:
                zone_shift_groups[key] = []
            zone_shift_groups[key].append(student)
        
        # Calculate T-scores for each student
        for student in all_students:
            key = f"{student.rrb_zone}_{student.shift}"
            zone_shift_students = zone_shift_groups[key]
            
            # Calculate T-scores for different comparison groups
            if student.is_reexam:
                reexam_students = [s for s in zone_shift_students if s.is_reexam]
                all_students_in_group = zone_shift_students
                
                t_scores_reexam, overall_reexam, _ = calculate_t_scores_and_overall(reexam_students, student)
                t_scores_all, overall_all, _ = calculate_t_scores_and_overall(all_students_in_group, student)
                
                csv_data.append({
                    'Roll_No': student.roll_no,
                    'Is_ReExam': student.is_reexam,
                    'RRB_Zone': student.rrb_zone,
                    'Exam_Date': student.exam_date.strftime('%Y-%m-%d'),
                    'Shift': student.shift,
                    'CBT2_Marks': student.cbt2_marks,
                    
                    'Memory_Raw_Score': round(student.memory_raw_score, 2),
                    'Directions_Raw_Score': round(student.directions_raw_score, 2),
                    'Depth_Raw_Score': round(student.depth_raw_score, 2),
                    'Concentration_Raw_Score': round(student.concentration_raw_score, 2),
                    'Perceptual_Raw_Score': round(student.perceptual_raw_score, 2),
                    
                    'Memory_T_Score_ReExam_Only': round(t_scores_reexam['memory'], 2),
                    'Directions_T_Score_ReExam_Only': round(t_scores_reexam['directions'], 2),
                    'Depth_T_Score_ReExam_Only': round(t_scores_reexam['depth'], 2),
                    'Concentration_T_Score_ReExam_Only': round(t_scores_reexam['concentration'], 2),
                    'Perceptual_T_Score_ReExam_Only': round(t_scores_reexam['perceptual'], 2),
                    'Overall_Score_ReExam_Only': round(overall_reexam, 2),
                    
                    'Memory_T_Score_All': round(t_scores_all['memory'], 2),
                    'Directions_T_Score_All': round(t_scores_all['directions'], 2),
                    'Depth_T_Score_All': round(t_scores_all['depth'], 2),
                    'Concentration_T_Score_All': round(t_scores_all['concentration'], 2),
                    'Perceptual_T_Score_All': round(t_scores_all['perceptual'], 2),
                    'Overall_Score_All': round(overall_all, 2)
                })
            else:
                non_reexam_students = [s for s in zone_shift_students if not s.is_reexam]
                all_students_in_group = zone_shift_students
                
                t_scores_non_reexam, overall_non_reexam, _ = calculate_t_scores_and_overall(non_reexam_students, student)
                t_scores_all, overall_all, _ = calculate_t_scores_and_overall(all_students_in_group, student)
                
                csv_data.append({
                    'Roll_No': student.roll_no,
                    'Is_ReExam': student.is_reexam,
                    'RRB_Zone': student.rrb_zone,
                    'Exam_Date': student.exam_date.strftime('%Y-%m-%d'),
                    'Shift': student.shift,
                    'CBT2_Marks': student.cbt2_marks,
                    
                    'Memory_Raw_Score': round(student.memory_raw_score, 2),
                    'Directions_Raw_Score': round(student.directions_raw_score, 2),
                    'Depth_Raw_Score': round(student.depth_raw_score, 2),
                    'Concentration_Raw_Score': round(student.concentration_raw_score, 2),
                    'Perceptual_Raw_Score': round(student.perceptual_raw_score, 2),
                    
                    'Memory_T_Score_NonReExam_Only': round(t_scores_non_reexam['memory'], 2),
                    'Directions_T_Score_NonReExam_Only': round(t_scores_non_reexam['directions'], 2),
                    'Depth_T_Score_NonReExam_Only': round(t_scores_non_reexam['depth'], 2),
                    'Concentration_T_Score_NonReExam_Only': round(t_scores_non_reexam['concentration'], 2),
                    'Perceptual_T_Score_NonReExam_Only': round(t_scores_non_reexam['perceptual'], 2),
                    'Overall_Score_NonReExam_Only': round(overall_non_reexam, 2),
                    
                    'Memory_T_Score_All': round(t_scores_all['memory'], 2),
                    'Directions_T_Score_All': round(t_scores_all['directions'], 2),
                    'Depth_T_Score_All': round(t_scores_all['depth'], 2),
                    'Concentration_T_Score_All': round(t_scores_all['concentration'], 2),
                    'Perceptual_T_Score_All': round(t_scores_all['perceptual'], 2),
                    'Overall_Score_All': round(overall_all, 2)
                })
        
        # Create DataFrame and save to CSV
        df = pd.DataFrame(csv_data)
        
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        df.to_csv(temp_file.name, index=False)
        temp_file.close()
        
        return send_file(temp_file.name, as_attachment=True, download_name='cbat_reports.csv')
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)