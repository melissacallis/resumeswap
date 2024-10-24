import os
import io
from django.shortcuts import render
from django.http import HttpResponse, FileResponse
from google.generativeai import configure, GenerativeModel
from .forms import JobDescriptionForm

from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from django.views.decorators.csrf import csrf_exempt
from django.templatetags.static import static
from weasyprint import HTML, CSS

import tempfile
from django.template.loader import render_to_string
import re

# Configure the Gemini API key
gemini_api_key = os.environ.get("GEMINI_API_KEY")
configure(api_key=gemini_api_key)

# Create the Gemini model instance
model = GenerativeModel('gemini-pro')

def generate_job_c(job_a, job_b):
    prompt = f"""
You are an assistant helping transform a user's resume to align with a job description. 

The user's current experience (Job A) is:

'{job_a}'

The target job description (Job B) is:

'{job_b}'

Instructions:

1. **Don’t copy**: Don’t use any parts of Job B word-for-word, except for technical terms or job titles.  
2. **Be honest**: Don’t make up any new skills or experience that aren’t already listed in Job A. Just focus on making their existing experience sound closer to Job B. 
3. **Reword**: Take what Job B asks for and reword what the person has done in Job A to match it.  
4. **Make it sound better**: Adjust the skills and tasks from Job A to match about 80% of what Job B wants. Use fancy words or industry terms from Job B where it makes sense.  
5. **Professional Summary**: Start with a short paragraph about the person’s skills, accomplishments, and goals. This should be based on Job A but written to match what Job B is asking for. Then incorporate this summary:
    The Data Science Master’s Program at Eastern University helped me build a strong foundation in analyzing data, developing insightful reports, solving complex problems, automating tasks, 
    and working effectively with cross-functional teams. I would draw on these skills to monitor performance, ensure data-driven decision-making, and collaborate with stakeholders to optimize processes. 
    My technical background would enable me to implement smarter strategies, driving higher efficiency and maintaining high-quality standards across all programs.
6. **Key Skills and Accomplishments**: After the summary, make a section called **'Key Skills and Accomplishments'** with bullet points. Each point should list something the person did in Job A, but make it sound like it fits Job B.  
7. **Keep it real**: Stay true to what the person really did in Job A. If Job B mentions tasks that are way more advanced, simplify them to match what the person actually did.  
8. **Simplify advanced stuff**: If Job B talks about leading a big team but Job A only involves working with small groups or alone, make sure to reflect that difference.  
9. **Use easy language**: Rewrite the descriptions of Job A and Job B so they sound simple and easy to understand, like a high school student wrote them.

Make sure the output format strictly follows this structure:

**Professional Summary:**

[The professional summary as a single paragraph.]

**Key Skills and Accomplishments:**

- [Skill or accomplishment 1]
- [Skill or accomplishment 2]
- [Skill or accomplishment 3]
[...]

Ensure that both sections are distinct and follow the format above. No other structure should be included.
    """

    response = model.generate_content(prompt)
    
    # Debugging output to check structure in terminal
    print(response.text)
    
    

    
    return response.text

# Assuming the generate_job_c function is in a file called job_generation.py
@csrf_exempt
def home(request):
    if request.method == 'POST':
        # Process the form data
        name = request.POST['name']
        job_title = request.POST['job_title']
        linkedin = request.POST['linkedin']
        email = request.POST['email']
        phone = request.POST['phone']
        city = request.POST['city']
        job_a = request.POST['job_a']
        job_b = request.POST['job_b']
        certifications = request.POST['certifications']
        schools = request.POST.getlist('school[]')
        degrees = request.POST.getlist('degree[]')
        start_dates = request.POST.getlist('start_date[]')
        end_dates = request.POST.getlist('end_date[]')
        skills = request.POST['skills']

        education = list(zip(schools, degrees, start_dates, end_dates))


        # Generate resume content
        job_c_output = generate_job_c(job_a, job_b)

        # Ensure proper parsing
        professional_summary, responsibilities = parse_job_c_output(job_c_output)

        # Render the output.html with the prefilled fields for review
        return render(request, 'transferx/output.html', {
            'name': name,
            'job_title': job_title,
            'linkedin': linkedin,
            'email': email,
            'phone': phone,
            'city': city,
            'professional_summary': professional_summary,  # Professional Summary
            'responsibilities': responsibilities,  # Job Responsibilities
            'certifications': certifications,
            'education': education,
            'skills': skills,
        })

    # If not POST, render the home.html form
    return render(request, 'transferx/home.html')


@csrf_exempt
def generate_pdf(request):
    if request.method == 'POST':
        # Collect form data
        name = request.POST.get('name')
        job_title = request.POST.get('job_title')
        linkedin = request.POST.get('linkedin')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        city = request.POST.get('city')
        professional_summary = request.POST.get('professional_summary')

        # Deserialize responsibilities back into a list
        responsibilities_raw = request.POST.get('responsibilities', '')
        responsibilities = [resp.strip() for resp in responsibilities_raw.split('|') if resp.strip()]

        # Deserialize education back into a list of tuples
        education_raw = request.POST.get('education', '')
        education = [tuple(edu.split('~~')) for edu in education_raw.split('|') if edu.strip() and len(edu.split('~~')) == 4]

        # Certifications and skills
        certifications = request.POST.get('certifications', '')
        skills = request.POST.get('skills', '')

        # Split skills and certifications by commas into lists
        skills = [skill.strip() for skill in request.POST.get('skills', '').split(',')]
        # Split certifications and skills correctly by commas
        #certifications = [cert.strip() for cert in certifications.split(',') if cert.strip()]
        #skills = [skill.strip() for skill in skills.split(',') if skill.strip()]

        

        #certifications = [cert.strip() for cert in request.POST.get('certifications', '').split(',')]
        # Process certifications: split by commas, then link previous word to the following URL
        # Process certifications: split by commas, then link previous word to the following URL
        certifications_raw = request.POST.get('certifications', '')
        certifications = []
        
        # Regex to detect URLs (http:// or https://)
        url_regex = re.compile(r'(http[s]?://[^\s]+)')
        
        certs = certifications_raw.split(',')
        for i, cert in enumerate(certs):
            cert = cert.strip()  # Remove any extra spaces or line breaks
            # Clean up URLs (remove any extra line breaks or invalid characters)
            cert = cert.replace('\n', '').replace('\r', '')  # Remove line breaks from URL
            
            # Check if this is a URL
            if url_regex.match(cert) and i > 0:
                # Link the previous certification to this URL
                certifications[-1] = (certs[i - 1].strip(), cert)
            else:
                # Add as plain text if it's not a URL
                certifications.append((cert, None))


        # Prepare context for the template
        context = {
            'name': name,
            'job_title': job_title,
            'linkedin': linkedin,
            'email': email,
            'phone': phone,
            'city': city,
            'professional_summary': professional_summary,
            'responsibilities': responsibilities,  # Pass as a list
            'education': education,  # Pass as a list of tuples
            'certifications': certifications,
            'skills': skills,
        }

        #education_raw = request.POST.get('education', '')
        print("Raw education data:", education_raw)  # Debugging: check if education data is passed correctly
        #education = [tuple(edu.split(',')) for edu in education_raw.split('|') if len(edu.split(',')) == 4]
        print("Parsed education data:", education)  # Debugging: check the parsed data

        html_string = render_to_string('transferx/resume_pdf.html', context)
        print(html_string)  # Add this to debug the HTML content before PDF generation
        #return HttpResponse(html_string)  # Return HTML to check it in the browser
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{name}_Resume.pdf"'
        HTML(string=html_string).write_pdf(response)

        return response









def parse_job_c_output(job_c_output):
    if not job_c_output:
        return "", []  # Return empty values if there's no content

    # Use a flexible regex to split the text into the two main sections
    # Capture both "Professional Summary" and "Key Skills and Accomplishments" in separate groups
    match = re.search(r'\*\*Professional Summary:\*\*(.*?)\*\*Key Skills and Accomplishments:\*\*(.*)', job_c_output, re.DOTALL)

    if match:
        # Extract the professional summary and responsibilities sections
        professional_summary = match.group(1).strip()  # Group 1 is the professional summary text
        responsibilities_section = match.group(2).strip()  # Group 2 is the key skills and accomplishments

        # Split the responsibilities by newlines (each starting with a dash)
        responsibilities = [resp.strip('- ') for resp in responsibilities_section.split('\n') if resp.strip() and resp.endswith('.')]

        return professional_summary, responsibilities
    else:
        # If the structure is not as expected, log a warning for debugging
        print("Warning: Unexpected Gemini output format.")
        return "", []


@csrf_exempt
def load_edit_resume(request):
    if request.method == 'POST':
        # Collect data sent from output.html
        name = request.POST.get('name')
        job_title = request.POST.get('job_title')
        linkedin = request.POST.get('linkedin')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        city = request.POST.get('city')
        professional_summary = request.POST.get('professional_summary')
        responsibilities = request.POST.get('responsibilities', '').split('|')
        certifications = request.POST.get('certifications', '').split(',')
        education = [tuple(edu.split('~~')) for edu in request.POST.get('education', '').split('|')]
        skills = request.POST.get('skills', '').split(',')

        # Prepare context with the data to be passed to the edit_resume.html template
        context = {
            'name': name,
            'job_title': job_title,
            'linkedin': linkedin,
            'email': email,
            'phone': phone,
            'city': city,
            'professional_summary': professional_summary,
            'responsibilities': responsibilities,
            'certifications': certifications,
            'education': education,
            'skills': skills,
        }

        # Render the edit_resume.html template with the pre-filled data
        return render(request, 'transferx/edit_resume.html', context)

    # If not a POST request, redirect to the home page or handle accordingly
    return redirect('home')
























