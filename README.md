#  SmartTour: AI-Powered Travel E-Commerce Platform

![Next.js](https://img.shields.io/badge/Next.js-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)
![Machine Learning](https://img.shields.io/badge/Machine_Learning-F7931E?style=for-the-badge&logo=scikit-learn&logoColor=white)
![LLM Llama 3](https://img.shields.io/badge/LLM-Llama_3-0467DF?style=for-the-badge)

##  Project Overview
**SmartTour** is a comprehensive, multi-actor E-commerce platform designed for the travel industry. It seamlessly connects four key entities: **Customers, Tour Guides, Suppliers, and Administrators**. 

Moving beyond traditional CRUD applications, this project deeply integrates **Machine Learning (Collaborative Filtering)** and **Generative AI (Llama 3 with Hybrid RAG)** to provide highly personalized user experiences. Furthermore, it implements a highly scalable **Real-time communication architecture using CDC (Change Data Capture)** and automates complex financial workflows.

---

##  Key Features & Technical Highlights (Why this project stands out)

### 1.  AI Chatbot with Hybrid Intent Detection & Hybrid RAG
* **Problem:** Large Language Models (LLMs) often suffer from **hallucinations** (inventing non-existent tours or pricing details).
* **Solution:** Developed a custom local AI Agent using **Ollama (Llama 3)**. I implemented a **Hybrid Intent Detection** system using Regular Expressions (Regex) to extract critical parameters (Budget, Destination, and Duration) with 100% precision before querying.
* **Mechanism:** The backend performs a Hybrid RAG approach by executing **Dynamic SQL Queries** on the real PostgreSQL database based on the detected intent. The fetched data is injected into the System Prompt as context, while enforcing strict JSON formatting constraints. This completely eliminates hallucinations and allows the Frontend to render dynamic UI Cards inside the chat window.

### 2.  Machine Learning Recommendation Engine
* **Algorithm:** Implemented **Item-based Collaborative Filtering** using `scikit-learn` and `Pandas`.
* **Data Processing:** The model dynamically weighs real-world user behaviors from log tables: **Orders** (5 pts), **Reviews** (1-5 pts), and **Tour Views** (1 pt) to generate a dense User-Item matrix and calculates Cosine Similarity.
* **Cold-Start Handling:** Engineered a fallback logic. For new users with no historical logs, the system automatically surfaces **Popular Tours** to prevent empty recommendations. For existing users, it mixes 80% behavior-based recommendations with 20% randomly shuffled new tours to increase visibility for new suppliers.
* **Automation:** Configured `APScheduler` combined with Python's `threading.Lock()` to handle background model retraining every 3 hours during low-traffic periods, preventing memory leaks and race conditions.

### 3.  High-Performance Real-time Chat (Supabase CDC)
* **Optimization:** Instead of using traditional `Socket.io` (which consumes heavy RAM on Python servers and requires stateful management), I implemented **Supabase Change Data Capture (CDC)**.
* **Mechanism:** The Next.js frontend listens directly to PostgreSQL database insertion events via real-time webhooks. Combined with **Optimistic UI Updates**, this achieves near-zero latency messaging between Customers and Tour Guides while keeping the Flask backend strictly **Stateless**.

---

##  Tech Stack

### **Frontend**
- **Framework:** Next.js 14 (App Router), React.js
- **Styling & UI:** Tailwind CSS
- **Real-time Engine:** Supabase Real-time JS Client (CDC)

### **Backend**
- **Framework:** Python 3, Flask (RESTful API Architecture)
- **Database ORM:** SQLAlchemy, PostgreSQL (hosted on Supabase)
- **AI & ML:** Scikit-learn, Pandas, NumPy, Ollama (Llama 3 running locally)
- **Authentication:** Flask-JWT-Extended
- **Task Scheduling:** APScheduler

### **DevOps & Integrations**
- **Payment Gateways:** Stripe API, VNPay API
- **Deployment Strategy:** Local Host (Development Environment with high-performance GPU/RAM optimized for Local LLMs). *Architecture ready for Nginx Reverse Proxy & SSL (Certbot) for production.*

---

##  My Contributions (Role: Fullstack & AI Engineer)

As a core developer of this project, I took full ownership of the most architecturally challenging modules:
1. **Designed & Engineered the Hybrid RAG AI Chatbot:** Built the local Llama 3 deployment flow, wrote the Regex-based Hybrid Intent extractor, and created the JSON output parser with an automated **SQL Fallback mechanism** to prevent UI breakage.
2. **Developed the Recommendation Pipeline:** Implemented the scoring matrix logic using Pandas, integrated Cosine Similarity calculations, and resolved the **Cold Start** problem for new users.
3. **System Automation:** Set up `APScheduler` with thread-locking mechanisms to run heavy matrix recalculations safely without disrupting active users.
4. **Database & API Architecture:** Formulated the dynamic SQLAlchemy querying logic, structured database schemas on Supabase, and secured endpoints using role-based JWT decorators.

---

##  Getting Started (Local Development)

### 1. Clone the repository
```bash
git clone [https://github.com/your-username/smart-tour-platform.git](https://github.com/your-username/smart-tour-platform.git)
cd smart-tour-platform
