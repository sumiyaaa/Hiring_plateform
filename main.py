from datetime import datetime
import os
from uuid import uuid4

from fastapi import File, UploadFile, HTTPException
from fastapi import FastAPI, Form, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi_mail import ConnectionConfig, MessageSchema, FastMail
from pydantic import EmailStr
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session, joinedload
import hashlib

from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

import models
from models import Recruiter, Candidate, Resume, CandidateProfile, JobPost, JobType, JobApplication, ResumeInteraction
from database import engine, Base, get_db

app = FastAPI()

# Add session middleware
app.add_middleware(SessionMiddleware, secret_key="your-secret-key")

# Mount the uploads directory
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Create the database tables
Base.metadata.create_all(bind=engine)

# Serve static files from the 'static' directory
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/candidate", response_class=HTMLResponse)
async def candidate_login(request: Request):
    return templates.TemplateResponse("candidate_login.html", {"request": request})

@app.get("/candidate/signup", response_class=HTMLResponse)
async def candidate_signup(request: Request):
    return templates.TemplateResponse("candidate_signup.html", {"request": request})

# @app.post("/candidate/login")
# async def candidate_login_post(email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
#     candidate = db.query(Candidate).filter(Candidate.email == email).first()
#     if candidate and candidate.hashed_password == hashlib.sha256(password.encode()).hexdigest():
#         return RedirectResponse(url="/dashboard", status_code=303)  # Redirect to dashboard
#     return HTMLResponse("Invalid email or password", status_code=400)

@app.post("/candidate/login")
async def candidate_login_post(
        email: str = Form(...),
        password: str = Form(...),
        db: Session = Depends(get_db),
        request: Request = None
):
    candidate = db.query(Candidate).filter(Candidate.email == email).first()
    if candidate and candidate.hashed_password == hashlib.sha256(password.encode()).hexdigest():
        request.session['user_role'] = 'candidate'
        request.session['user_id'] = candidate.id  # Store candidate ID in session
        return RedirectResponse(url="/dashboard", status_code=303)
    return HTMLResponse("Invalid email or password", status_code=400)


@app.post("/candidate/signup")
async def candidate_signup_post(email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if db.query(Candidate).filter(Candidate.email == email).first():
        return HTMLResponse("Email already registered", status_code=400)

    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    new_candidate = Candidate(email=email, hashed_password=hashed_password)
    db.add(new_candidate)
    db.commit()
    return RedirectResponse(url="/candidate", status_code=303)  # Redirect to login

@app.get("/profile", response_class=HTMLResponse)
async def view_profile(request: Request, db: Session = Depends(get_db)):
    candidate_id = request.session.get('user_id')
    if not candidate_id:
        return RedirectResponse(url="/candidate", status_code=303)

    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        return HTMLResponse("Profile not found", status_code=404)

    profile = db.query(CandidateProfile).filter(CandidateProfile.candidate_id == candidate_id).first()
    if not profile:
        profile = CandidateProfile(candidate_id=candidate_id)

    return templates.TemplateResponse("profile.html", {"request": request, "profile": profile})

@app.post("/profile/update")
async def update_profile(
        name: str = Form(...),
        education: str = Form(...),
        skills: str = Form(...),
        experience: str = Form(...),
        linkedin: str = Form(...),
        github: str = Form(...),
        phone_number: str = Form(...),
        photo: UploadFile = File(None),  # Make photo optional
        db: Session = Depends(get_db),
        request: Request = None
):
    candidate_id = request.session.get('user_id')
    if not candidate_id:
        return RedirectResponse(url="/candidate", status_code=303)

    candidate_profile = db.query(CandidateProfile).filter(CandidateProfile.candidate_id == candidate_id).first()
    if not candidate_profile:
        return HTMLResponse("Profile not found", status_code=404)

    # Update profile details
    candidate_profile.name = name
    candidate_profile.education = education
    candidate_profile.skills = skills
    candidate_profile.experience = experience
    candidate_profile.linkedin = linkedin
    candidate_profile.github = github
    candidate_profile.phone_number = phone_number

    # Handle photo upload
    if photo:
        file_extension = photo.filename.split(".")[-1]
        file_name = f"{uuid4()}.{file_extension}"
        file_path = os.path.join("uploads", file_name)
        with open(file_path, "wb") as buffer:
            buffer.write(photo.file.read())
        candidate_profile.photo_url = file_path

    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/resume", response_class=HTMLResponse)
async def upload_resume_form(request: Request):
    return templates.TemplateResponse("resume_upload.html", {"request": request})

@app.post("/resume/upload")
async def upload_resume(
        title: str = Form(...),
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        request: Request = None
):
    candidate_id = request.session.get('user_id')  # Assuming user_id is stored in the session
    if not candidate_id:
        return RedirectResponse(url="/candidate", status_code=303)

    # Save the uploaded file
    file_extension = file.filename.split(".")[-1]
    file_name = f"{uuid4()}.{file_extension}"
    file_path = file_name  # Save file without the 'uploads/' prefix

    with open(os.path.join("uploads", file_path), "wb") as buffer:
        buffer.write(file.file.read())

    # Create a new Resume entry in the database
    new_resume = Resume(title=title, file_path=file_path, candidate_id=candidate_id)
    db.add(new_resume)
    db.commit()
    db.refresh(new_resume)  # Now new_resume.id is available

    # Generate a link using the resume ID
    base_url = "http://127.0.0.1:8000"  # Replace with your actual base URL
    resume_link = f"{base_url}/resume/view/{new_resume.id}"  # Use resume ID in the link

    # Return the link in the success template
    return templates.TemplateResponse("resume_upload_success.html", {"request": request, "resume_link": resume_link})

@app.get("/resume/view/{resume_id}")
async def view_resume(resume_id: int, db: Session = Depends(get_db)):
    # Fetch the resume using the resume ID
    resume = db.query(Resume).filter(Resume.id == resume_id).first()

    if not resume:
        return
    # Serve the resume file
    resume_file_path = os.path.join("uploads", resume.file_path)
    return FileResponse(resume_file_path)


# @app.post("/resume/upload")
# async def upload_resume(
#         title: str = Form(...),
#         file: UploadFile = File(...),
#         db: Session = Depends(get_db),
#         request: Request = None
# ):
#     candidate_id = request.session.get('user_id')  # Assuming user_id is stored in the session
#     if not candidate_id:
#         return RedirectResponse(url="/candidate", status_code=303)
#
#     # Save the uploaded file
#     file_extension = file.filename.split(".")[-1]
#     file_name = f"{uuid4()}.{file_extension}"
#     file_path = file_name  # Save file without the 'uploads/' prefix
#
#     with open(os.path.join("uploads", file_path), "wb") as buffer:
#          buffer.write(file.file.read())
#
#     # Create a new Resume entry in the database
#     new_resume = Resume(title=title, file_path=file_path, candidate_id=candidate_id)
#     db.add(new_resume)
#     db.commit()
#     db.refresh(new_resume)
#
#     # # Generate a link for the resume
#     # base_url = "http://127.0.0.1:8000"
#     # resume_link = f"{base_url}/resume/view/{new_resume.id}"
#     #
#     # return templates.TemplateResponse("resume_upload_success.html", {"request": request, "resume_link": resume_link})
#
#
#  #    # Generate a complete URL for the resume
#     base_url = "http://127.0.0.1:8000"  # Replace with your actual base URL if different
#     resume_link = f"{base_url}/uploads/{new_resume.file_path}"
#  #   return JSONResponse(content={"success": True, "resume_link": resume_link})
#
#     return templates.TemplateResponse("resume_upload_success.html", {"request": request, "resume_link": resume_link})


# job list view
@app.get("/jobs", response_class=HTMLResponse)
async def list_jobs(request: Request, db: Session = Depends(get_db)):
    try:
        jobs = db.query(JobPost).all()
        return templates.TemplateResponse("jobs.html", {"request": request, "jobs": jobs})
    except Exception as e:
        # Log the exception and return an error response
        print(f"Error fetching jobs: {e}")
        return HTMLResponse("An error occurred while fetching job listings.", status_code=500)

# Quick apply
@app.get("/apply/{job_id}", response_class=HTMLResponse)
async def apply_for_job(request: Request, job_id: int, db: Session = Depends(get_db)):
    job = db.query(JobPost).filter(JobPost.id == job_id).first()
    if not job:
        return RedirectResponse(url="/jobs", status_code=303)
    return templates.TemplateResponse("quick_apply.html", {"request": request, "job": job})

# quick apply submission
@app.post("/submit-application/{job_id}")
async def submit_application(
        job_id: int,
        name: str = Form(...),
        email: str = Form(...),
        resume_link: str = Form(...),
        db: Session = Depends(get_db),
        request: Request = None
):
    job = db.query(JobPost).filter(JobPost.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Create and save the job application
    application = JobApplication(
        job_id=job_id,
        name=name,
        email=email,
        resume_link=resume_link
    )
    db.add(application)
    db.commit()

    return RedirectResponse(url="/jobs", status_code=303)  # Redirect to job listings after applying

@app.get("/recruiter", response_class=HTMLResponse)
async def recruiter_login(request: Request):
    return templates.TemplateResponse("recruiter_login.html", {"request": request})

@app.get("/recruiter/signup", response_class=HTMLResponse)
async def recruiter_signup(request: Request):
    return templates.TemplateResponse("recruiter_signup.html", {"request": request})


@app.post("/recruiter/login")
async def login(
        email: str = Form(...),
        password: str = Form(...),
        db: Session = Depends(get_db),
        request: Request = None
):
    recruiter = db.query(Recruiter).filter(Recruiter.email == email).first()
    if recruiter and recruiter.hashed_password == hashlib.sha256(password.encode()).hexdigest():
        request.session['user_id'] = recruiter.id  # Store user ID in session
        request.session['user_role'] = 'recruiter'  # Set the session role
        return RedirectResponse(url="/dashboard", status_code=303)  # Redirect to dashboard
    return HTMLResponse("Invalid email or password", status_code=400)

@app.post("/recruiter/signup")
async def signup(email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if db.query(Recruiter).filter(Recruiter.email == email).first():
        return HTMLResponse("Email already registered", status_code=400)

    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    new_recruiter = Recruiter(email=email, hashed_password=hashed_password)
    db.add(new_recruiter)
    db.commit()
    return RedirectResponse(url="/recruiter", status_code=303)  # Redirect to login

# @app.get("/dashboard", response_class=HTMLResponse)
# async def dashboard(request: Request):
#     return templates.TemplateResponse("candidate_dashboard.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user_role = request.session.get('user_role')
    if user_role == "candidate":
        return templates.TemplateResponse("candidate_dashboard.html", {"request": request})
    elif user_role == "recruiter":
        return templates.TemplateResponse("recruiter_dashboard.html", {"request": request})
    else:
        return RedirectResponse(url="/", status_code=303)  # Redirect to homepage if user role is not set

# Job Post...
@app.get("/job_post", response_class=HTMLResponse)
async def job_post_form(request: Request):
    user_role = request.session.get('user_role')
    if user_role == "recruiter":
        return templates.TemplateResponse("job_post.html", {"request": request})
    return RedirectResponse(url="/recruiter", status_code=303)  # Redirect to recruiter login if not authenticated

@app.post("/job-post")
async def create_job_post(
        company_name: str = Form(...),
        job_title: str = Form(...),
        description: str = Form(...),
        skills: str = Form(...),
        job_type: JobType = Form(...),
        db: Session = Depends(get_db),
        request: Request = None
):
    recruiter_id = request.session.get('user_id')  # Assuming recruiter ID is stored in the session
    if not recruiter_id:
        return RedirectResponse(url="/recruiter", status_code=303)

    # Create and save the job post
    job_post = JobPost(
        company_name=company_name,
        job_title=job_title,
        description=description,
        skills=skills,
        job_type=job_type,
        recruiter_id=recruiter_id
    )
    db.add(job_post)
    db.commit()

    return RedirectResponse(url="/dashboard", status_code=303)  # Redirect to the dashboard after posting the job

@app.get("/applications", response_class=HTMLResponse)
async def view_applications(request: Request, db: Session = Depends(get_db)):
    recruiter_id = request.session.get('user_id')

    if not recruiter_id:
        return RedirectResponse(url="/login", status_code=303)

    # Fetch recruiter information (session id save during login)
    recruiter = db.query(Recruiter).filter(Recruiter.id == recruiter_id).first()

    if not recruiter:
        return HTMLResponse("Recruiter not found", status_code=404)

    # Fetch all job posts for this recruiter
    job_posts = db.query(JobPost).filter(JobPost.recruiter_id == recruiter_id).all()

    # Initialize a dictionary to hold job applications
    job_applications = {}

    for job in job_posts:
        # Fetch applications for each job post
        applications = db.query(JobApplication).filter(JobApplication.job_id == job.id).all()

        # Populate job_applications dictionary with job and its applications
        job_applications[job.id] = {
            "job": job,
            "applications": applications
        }

    # Pass the data to the template
    return templates.TemplateResponse("applications.html", {
        "request": request,
        "job_applications": job_applications
    })

@app.get("/logout")
async def logout(request: Request):
    # Clear session data
    request.session.clear()
    # Redirect to the candidate login page
    return RedirectResponse(url="/", status_code=303)

# resume interaction


@app.post("/resume_interaction")
async def log_interaction(
        resume_link: str = Form(...),
        interaction_type: str = Form(...),
        db: Session = Depends(get_db),
        request: Request = None
):
    # logging.info(f"Received interaction: resume_link={resume_link}, interaction_type={interaction_type}")
    try:
        # Example resume link: "http://127.0.0.1:8000/resume/view/37"
        # Strip query parameters and fragment identifiers if any
        url_path = resume_link.split('?')[0].split('#')[0]

        # Split the URL by '/' and remove trailing empty segments
        path_parts = url_path.rstrip('/').split('/')

        # Ensure there are at least two segments ("/resume/view/{resume_id}")
        if len(path_parts) < 2:
            raise HTTPException(status_code=400, detail="Invalid resume link format")

        # Extract the resume ID from the URL
        resume_id_str = path_parts[-1]
        if resume_id_str.isdigit():
            resume_id = int(resume_id_str)
        else:
            raise HTTPException(status_code=400, detail="Invalid resume link format")

        # Get the recruiter ID from the session
        recruiter_id = request.session.get('user_id')
        if not recruiter_id:
            raise HTTPException(status_code=401, detail="Unauthorized")

        # Check if the resume exists
        resume = db.query(Resume).filter(Resume.id == resume_id).first()
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")

        # Log the interaction
        new_interaction = ResumeInteraction(
            resume_id=resume_id,
            recruiter_id=recruiter_id,
            interaction_type=interaction_type,  # 'view' or 'download'
            timestamp=datetime.utcnow()
        )
        db.add(new_interaction)
        db.commit()
        db.refresh(new_interaction)

        # Use the stored file path from the resume object
        resume_pdf_path = os.path.join("uploads", resume.file_path)

        # Check if the file exists
        if not os.path.exists(resume_pdf_path):
            raise HTTPException(status_code=404, detail="File not found")

        # Return the appropriate response based on the interaction_type
        if interaction_type == "view":
            # Return the PDF to be viewed in the browser
            return FileResponse(resume_pdf_path, media_type='application/pdf')

        elif interaction_type == "download":
            # Trigger a direct download of the PDF
            return FileResponse(resume_pdf_path, media_type='application/pdf', filename=f"resume_{resume_id}.pdf")

        else:
            raise HTTPException(status_code=400, detail="Invalid interaction type")

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



@app.get("/resume_insights", response_class=HTMLResponse)
async def resume_insights(request: Request, db: Session = Depends(get_db)):
    candidate_id = request.session.get('user_id')
    if not candidate_id:
        return RedirectResponse(url="/candidate", status_code=303)

    # Fetch all resumes for this candidate
    resumes = db.query(Resume).filter(Resume.candidate_id == candidate_id).all()
    if not resumes:
        return HTMLResponse("No resumes found.", status_code=404)

    resume_insights_data = []

    for resume in resumes:
        # # Fetch all interactions for each resume
        # interactions = db.query(ResumeInteraction).filter(ResumeInteraction.resume_id == resume.id).all()

        # Fetch all interactions for each resume, eagerly loading the recruiter
        interactions = db.query(ResumeInteraction).filter(ResumeInteraction.resume_id == resume.id).options(joinedload(ResumeInteraction.recruiter)).all()


        # # Fetch job application details
        # job_application = db.query(JobApplication).filter(JobApplication.resume_id == resume.id).first()

        # Calculate number of views and downloads
        views = len([i for i in interactions if i.interaction_type == "view"])
        downloads = len([i for i in interactions if i.interaction_type == "download"])

        interaction_data = []
        for interaction in interactions:
              recruiter_email = interaction.recruiter.email if interaction.recruiter else "Unknown Recruiter"
              interaction_data.append({
                "recruiter_email": recruiter_email,  # Use recruiter's email
                "interaction_type": interaction.interaction_type,
                "timestamp": interaction.timestamp
         })

        resume_insights_data.append({
            "resume": resume,
            "views": views,
            "downloads": downloads,
            "interactions": interaction_data,
        })

    # Pass the insights data to the template
    return templates.TemplateResponse("resume_insights.html", {
        "request": request,
        "resume_insights_data": resume_insights_data
    })

# accept and reject route
