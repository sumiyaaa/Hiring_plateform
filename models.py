import enum
from datetime import datetime

from sqlalchemy import Column, Integer, String, ForeignKey, Text, Enum, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    file_path = Column(String)
    candidate_id = Column(Integer, ForeignKey('candidates.id'))

    candidate = relationship("Candidate", back_populates="resumes")
    interactions = relationship("ResumeInteraction", back_populates="resume")


class Candidate(Base):
    __tablename__ = 'candidates'

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True)  # Specify length for VARCHAR
    hashed_password = Column(String(255))  # Specify length for VARCHAR

    profile = relationship("CandidateProfile", back_populates="candidate", uselist=False)
    resumes = relationship("Resume", back_populates="candidate")


class CandidateProfile(Base):
    __tablename__ = 'candidate_profiles'

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id'))
    name = Column(String(255))
    education = Column(Text)
    skills = Column(Text)
    experience = Column(Text)
    linkedin = Column(String(255))
    github = Column(String(255))
    phone_number = Column(String(20))
    photo_url = Column(String(255))

    candidate = relationship("Candidate", back_populates="profile")


class Recruiter(Base):
    __tablename__ = 'recruiters'

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True)  # Specify length for VARCHAR
    hashed_password = Column(String(255))  # Specify length for VARCHAR

    job_posts = relationship("JobPost", back_populates="recruiter")
    interactions = relationship("ResumeInteraction", back_populates="recruiter")


class JobType(enum.Enum):
    ONSITE = "Onsite"
    REMOTE = "Remote"
    HYBRID = "Hybrid"


class JobPost(Base):
    __tablename__ = "job_posts"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, nullable=False)
    job_title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    skills = Column(String, nullable=False)
    job_type = Column(Enum(JobType), nullable=False)
    recruiter_id = Column(Integer, ForeignKey("recruiters.id"))

    recruiter = relationship("Recruiter", back_populates="job_posts")
    applications = relationship("JobApplication", back_populates="job")


class JobApplication(Base):
    __tablename__ = "job_applications"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    resume_link = Column(String, nullable=False)
    job_id = Column(Integer, ForeignKey("job_posts.id"))

    job = relationship("JobPost", back_populates="applications")

class ResumeInteraction(Base):
    __tablename__ = 'resume_interactions'

    id = Column(Integer, primary_key=True, index=True)
    resume_id = Column(Integer, ForeignKey('resumes.id'))
    recruiter_id = Column(Integer, ForeignKey('recruiters.id'))
    interaction_type = Column(String)  # 'view' or 'download'
    timestamp = Column(DateTime, default=datetime.utcnow())

    resume = relationship("Resume", back_populates="interactions")

    recruiter = relationship("Recruiter",back_populates="interactions")
