from flask import Flask, render_template, request

app = Flask(__name__)

assignments = [
    {
        "id": 1,
        "title": "Cloud Computing Fundamentals",
        "subject": "Cloud Computing",
        "deadline": "2026-11-05"
    },
    {
        "id": 2,
        "title": "Python Programming",
        "subject": "Programming",
        "deadline": "2026-11-08"
    },
    {
        "id": 3,
        "title": "DevOps Introduction",
        "subject": "DevOps",
        "deadline": "2026-11-12"
    }
]


@app.route("/")
def home():
    return render_template("index.html", assignments=assignments)


@app.route("/assignments")
def view_assignments():
    return render_template(
        "assignments.html",
        assignments=assignments
    )


@app.route("/submit", methods=["GET", "POST"])
def submit_assignment():
    message = None

    if request.method == "POST":
        student_name = request.form.get("student_name", "").strip()
        assignment_id = request.form.get("assignment_id", "").strip()

        if student_name and assignment_id:
            message = (
                f"Thank you, {student_name}! "
                "Your submission request has been received."
            )
        else:
            message = "Please complete all fields."

    return render_template(
        "submit.html",
        assignments=assignments,
        message=message
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)