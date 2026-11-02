from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
import sqlite3, os, csv, io
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "rescuenet-dev-secret-change-me")
DB = os.path.join(os.path.dirname(__file__), "rescuenet.db")

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def priority_for(category, description, people):
    text = (category + " " + description).lower()
    critical_terms = ["trapped", "collapsed", "fire", "building collapse", "life threatening", "critical", "flooded", "injured"]
    high_terms = ["injured", "flood", "accident", "stranded", "medical", "smoke"]
    if any(x in text for x in critical_terms) or int(people or 0) >= 10:
        return "Critical", 95, "Potential immediate threat to life or multiple people affected."
    if any(x in text for x in high_terms) or int(people or 0) >= 4:
        return "High", 75, "Urgent assistance may be required; review promptly."
    if category.lower() in ["medical", "fire", "flood"]:
        return "High", 70, "Incident category commonly requires rapid response."
    return "Moderate", 45, "No critical indicator detected by the prototype rules."

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, password TEXT, role TEXT);
        CREATE TABLE IF NOT EXISTS incidents(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, category TEXT, description TEXT, location TEXT, lat REAL, lng REAL, people INTEGER DEFAULT 1, priority TEXT, risk_score INTEGER, rationale TEXT, status TEXT DEFAULT 'Reported', reporter_id INTEGER, assigned_team INTEGER, created_at TEXT);
        CREATE TABLE IF NOT EXISTS teams(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, specialty TEXT, members INTEGER, status TEXT, location TEXT);
        CREATE TABLE IF NOT EXISTS resources(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, category TEXT, quantity INTEGER, unit TEXT, location TEXT, status TEXT);
        CREATE TABLE IF NOT EXISTS shelters(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, location TEXT, capacity INTEGER, occupied INTEGER, contact TEXT);
        """)
        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            c.executemany("INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)", [
                ("System Administrator","admin@rescuenet.demo","admin123","admin"),
                ("Field Coordinator","team@rescuenet.demo","team123","team"),
                ("Demo Citizen","citizen@rescuenet.demo","citizen123","citizen")])
        if c.execute("SELECT COUNT(*) FROM teams").fetchone()[0] == 0:
            c.executemany("INSERT INTO teams(name,specialty,members,status,location) VALUES(?,?,?,?,?)", [
                ("Alpha Rescue Unit","Search & Rescue",8,"Available","North Zone"),
                ("Medical Response 01","Medical",5,"Available","Central Zone"),
                ("Fire & Safety Unit","Fire Response",6,"On Assignment","East Zone"),
                ("Flood Support Team","Flood & Evacuation",7,"Available","River Zone")])
        if c.execute("SELECT COUNT(*) FROM resources").fetchone()[0] == 0:
            c.executemany("INSERT INTO resources(name,category,quantity,unit,location,status) VALUES(?,?,?,?,?,?)", [
                ("First Aid Kits","Medical",42,"kits","Central Warehouse","Available"),
                ("Rescue Boats","Transport",6,"boats","River Depot","Available"),
                ("Drinking Water","Relief",320,"litres","North Warehouse","Available"),
                ("Emergency Blankets","Relief",150,"units","Central Warehouse","Available"),
                ("Portable Generators","Equipment",9,"units","East Depot","Available")])
        if c.execute("SELECT COUNT(*) FROM shelters").fetchone()[0] == 0:
            c.executemany("INSERT INTO shelters(name,location,capacity,occupied,contact) VALUES(?,?,?,?,?)", [
                ("Community Relief Centre","North Zone",180,94,"011-4000-1101"),
                ("Central School Shelter","Central Zone",120,72,"011-4000-1102"),
                ("Riverbank Safe Hall","River Zone",250,201,"011-4000-1103")])
        if c.execute("SELECT COUNT(*) FROM incidents").fetchone()[0] == 0:
            samples = [
                ("Water entering homes","Flood","Rising water reported in two streets; several families need assistance.","River Zone",28.6139,77.2090,8),
                ("Road accident","Medical","Two people injured after a road accident. First aid requested.","Central Zone",28.6200,77.2150,2),
                ("Smoke near market","Fire","Smoke visible near the market building. Cause not confirmed.","East Zone",28.6250,77.2250,3),
                ("Power outage","Infrastructure","Power outage affecting the residential block.","North Zone",28.6350,77.2050,1)]
            for s in samples:
                p, score, why = priority_for(s[1],s[2],s[6])
                c.execute("""INSERT INTO incidents(title,category,description,location,lat,lng,people,priority,risk_score,rationale,status,reporter_id,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (*s,p,score,why,"Reported",3,datetime.now().strftime("%Y-%m-%d %H:%M")))

init_db()

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped

def roles(*allowed):
    def deco(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if session.get("role") not in allowed:
                flash("You do not have permission to access that section.", "error")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return wrapped
    return deco

@app.context_processor
def inject_globals():
    return {"current_year": datetime.now().year}

@app.route("/")
def home():
    if session.get("user_id"): return redirect(url_for("dashboard"))
    return render_template("landing.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email=request.form.get("email","").strip().lower()
        password=request.form.get("password","")
        with db() as c: user=c.execute("SELECT * FROM users WHERE email=? AND password=?",(email,password)).fetchone()
        if user:
            session.update(user_id=user["id"], name=user["name"], role=user["role"], email=user["email"])
            return redirect(url_for("dashboard"))
        flash("Invalid email or password. Try a demo account below.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/dashboard")
@login_required
def dashboard():
    with db() as c:
        stats = {
            "total": c.execute("SELECT COUNT(*) FROM incidents").fetchone()[0],
            "active": c.execute("SELECT COUNT(*) FROM incidents WHERE status!='Resolved'").fetchone()[0],
            "critical": c.execute("SELECT COUNT(*) FROM incidents WHERE priority='Critical' AND status!='Resolved'").fetchone()[0],
            "resolved": c.execute("SELECT COUNT(*) FROM incidents WHERE status='Resolved'").fetchone()[0],
            "teams": c.execute("SELECT COUNT(*) FROM teams WHERE status='Available'").fetchone()[0],
        }
        incidents=c.execute("SELECT * FROM incidents ORDER BY id DESC LIMIT 7").fetchall()
        bycat=c.execute("SELECT category,COUNT(*) n FROM incidents GROUP BY category").fetchall()
        bystatus=c.execute("SELECT status,COUNT(*) n FROM incidents GROUP BY status").fetchall()
        resources=c.execute("SELECT * FROM resources ORDER BY quantity ASC LIMIT 5").fetchall()
    return render_template("dashboard.html",stats=stats,incidents=incidents,bycat=bycat,bystatus=bystatus,resources=resources)

@app.route("/incidents")
@login_required
def incidents():
    q=request.args.get("q","").strip()
    status=request.args.get("status","")
    sql="SELECT i.*,t.name team_name FROM incidents i LEFT JOIN teams t ON i.assigned_team=t.id WHERE 1=1"
    args=[]
    if q: sql+=" AND (i.title LIKE ? OR i.location LIKE ? OR i.category LIKE ?)"; args += [f"%{q}%"]*3
    if status: sql+=" AND i.status=?"; args.append(status)
    sql+=" ORDER BY CASE i.priority WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 ELSE 3 END, i.id DESC"
    with db() as c: rows=c.execute(sql,args).fetchall()
    return render_template("incidents.html",incidents=rows,q=q,status=status)

@app.route("/report", methods=["GET","POST"])
@login_required
def report():
    if request.method=="POST":
        title=request.form.get("title","").strip()
        category=request.form.get("category","Other")
        description=request.form.get("description","").strip()
        location=request.form.get("location","").strip()
        try:
            lat=float(request.form.get("lat") or 28.6139); lng=float(request.form.get("lng") or 77.2090)
            people=max(1,int(request.form.get("people") or 1))
        except ValueError:
            flash("Please enter valid numeric location and people values.","error"); return redirect(url_for("report"))
        if not title or not description or not location:
            flash("Please complete all required fields.","error"); return redirect(url_for("report"))
        priority,score,why=priority_for(category,description,people)
        with db() as c:
            c.execute("""INSERT INTO incidents(title,category,description,location,lat,lng,people,priority,risk_score,rationale,status,reporter_id,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(title,category,description,location,lat,lng,people,priority,score,why,"Reported",session["user_id"],datetime.now().strftime("%Y-%m-%d %H:%M")))
        flash(f"Incident submitted. Prototype risk assessment: {priority} ({score}/100).","success")
        return redirect(url_for("incidents"))
    return render_template("report.html")

@app.route("/incident/<int:iid>",methods=["GET","POST"])
@login_required
def incident_detail(iid):
    with db() as c:
        incident=c.execute("SELECT * FROM incidents WHERE id=?",(iid,)).fetchone()
        teams=c.execute("SELECT * FROM teams ORDER BY status,name").fetchall()
        if not incident: return "Incident not found",404
        if request.method=="POST" and session["role"] in ("admin","team"):
            status=request.form.get("status",incident["status"])
            team=request.form.get("team") or None
            c.execute("UPDATE incidents SET status=?,assigned_team=? WHERE id=?",(status,team,iid))
            if team: c.execute("UPDATE teams SET status='On Assignment' WHERE id=?",(team,))
            flash("Incident updated successfully.","success")
            return redirect(url_for("incident_detail",iid=iid))
    return render_template("incident_detail.html",incident=incident,teams=teams)

@app.route("/teams")
@login_required
def teams():
    with db() as c: rows=c.execute("SELECT t.*,COUNT(i.id) assignments FROM teams t LEFT JOIN incidents i ON i.assigned_team=t.id AND i.status!='Resolved' GROUP BY t.id ORDER BY t.id").fetchall()
    return render_template("teams.html",teams=rows)

@app.route("/resources")
@login_required
def resources():
    with db() as c: rows=c.execute("SELECT * FROM resources ORDER BY category,name").fetchall()
    return render_template("resources.html",resources=rows)

@app.route("/resources/update",methods=["POST"])
@login_required
@roles("admin","team")
def update_resource():
    rid=request.form.get("id",type=int); qty=request.form.get("quantity",type=int)
    if rid and qty is not None and qty>=0:
        with db() as c: c.execute("UPDATE resources SET quantity=? WHERE id=?",(qty,rid))
        flash("Resource inventory updated.","success")
    return redirect(url_for("resources"))

@app.route("/shelters")
@login_required
def shelters():
    with db() as c: rows=c.execute("SELECT * FROM shelters ORDER BY name").fetchall()
    return render_template("shelters.html",shelters=rows)

@app.route("/map")
@login_required
def map_view():
    with db() as c: rows=[dict(r) for r in c.execute("SELECT * FROM incidents WHERE lat IS NOT NULL AND lng IS NOT NULL ORDER BY id DESC").fetchall()]
    return render_template("map.html",incidents=rows)

@app.route("/analytics")
@login_required
def analytics():
    with db() as c:
        categories=c.execute("SELECT category,COUNT(*) n FROM incidents GROUP BY category").fetchall()
        priorities=c.execute("SELECT priority,COUNT(*) n FROM incidents GROUP BY priority").fetchall()
        statuses=c.execute("SELECT status,COUNT(*) n FROM incidents GROUP BY status").fetchall()
        total=c.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
        resolved=c.execute("SELECT COUNT(*) FROM incidents WHERE status='Resolved'").fetchone()[0]
    return render_template("analytics.html",categories=categories,priorities=priorities,statuses=statuses,total=total,resolved=resolved)

@app.route("/export/incidents.csv")
@login_required
def export_csv():
    with db() as c: rows=c.execute("SELECT id,title,category,location,people,priority,risk_score,status,created_at FROM incidents ORDER BY id DESC").fetchall()
    output=io.StringIO(); writer=csv.writer(output)
    writer.writerow(["ID","Title","Category","Location","People","Priority","Risk score","Status","Created"])
    writer.writerows([tuple(r) for r in rows])
    return Response(output.getvalue(),mimetype="text/csv",headers={"Content-Disposition":"attachment; filename=rescuenet_incidents.csv"})

@app.route("/api/incidents")
@login_required
def api_incidents():
    with db() as c: rows=c.execute("SELECT id,title,category,location,lat,lng,priority,status FROM incidents WHERE lat IS NOT NULL AND lng IS NOT NULL").fetchall()
    return jsonify([dict(r) for r in rows])

if __name__=="__main__":
    app.run(debug=True)
