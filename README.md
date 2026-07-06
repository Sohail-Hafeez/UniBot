# UniBot — A Chatbot for NUST & MCS Students

UniBot is a chatbot that answers questions for students of **NUST** (National University of Sciences and Technology, main campus in H-12, Islamabad) and **MCS** (Military College of Signals, a college of NUST located in Lalkurti, Rawalpindi).

If a new student asks "What documents do I need for admission?" or "What are the hostel rules?", UniBot answers using **real official university documents** — not guesses, not made-up answers.

This README explains everything about this project in plain, simple English. No confusing tech-talk without an explanation next to it. If you know nothing about AI or coding, you should still be able to understand what this project does and how it was built.

---

## Table of Contents

1. [The Problem This Solves](#the-problem-this-solves)
2. [The Big Idea (What is RAG?)](#the-big-idea-what-is-rag)
3. [The Journey — How This Was Built](#the-journey--how-this-was-built)
4. [How It Works, Step by Step](#how-it-works-step-by-step)
5. [Data Collection and Cleaning](#data-collection-and-cleaning)
6. [Problems We Faced and Fixed](#problems-we-faced-and-fixed)
7. [Tech Stack (Tools Used and Why)](#tech-stack-tools-used-and-why)
8. [Architecture (How the Pieces Fit Together)](#architecture-how-the-pieces-fit-together)
9. [Features](#features)
10. [Project Structure (What's in Each Folder)](#project-structure-whats-in-each-folder)
11. [How to Run This Project on Your Own Computer](#how-to-run-this-project-on-your-own-computer)
12. [Environment Variables (Secret Keys You Need)](#environment-variables-secret-keys-you-need)
13. [Deployment Plan (Putting It Online for Free)](#deployment-plan-putting-it-online-for-free)
14. [Future Ideas](#future-ideas)

---

## The Problem This Solves

Every year, new students join NUST and MCS. They all have the same questions:

- What documents do I need to submit?
- What are the hostel rules?
- How do I apply for a fee refund?
- What is the academic calendar?

Right now, students have to dig through websites full of PDFs to find answers, or ask seniors, or ask the admin office. That's slow and confusing.

UniBot fixes this by acting like a helpful senior student who has read every official document and can answer instantly, any time of day.

**One tricky detail**: NUST (main campus, H-12 Islamabad) and MCS (Lalkurti, Rawalpindi) are technically part of the same university, but they are **different physical campuses** with **different hostels, different facilities, and different day-to-day rules**. An answer that is correct for a NUST H-12 student can be wrong or confusing for an MCS student. UniBot had to be taught to tell these two apart — more on that below.

---

## The Big Idea (What is RAG?)

UniBot uses something called **RAG**, which stands for **Retrieval-Augmented Generation**. That sounds complicated, but the idea is simple. Think of it like an "open-book exam" for the AI:

- A normal AI chatbot (like a basic version of ChatGPT) answers questions using only what it "remembers" from its training. It can make mistakes or make things up — this is called "hallucinating."
- UniBot instead **looks up the real official documents first**, finds the exact paragraphs that answer the question, and **then** writes an answer using only that real information.

It's the difference between a student answering an exam question from memory (risky, might be wrong) versus a student who is allowed to open the official course book, find the right page, and then answer (much safer, much more accurate).

That's why UniBot's answers are grounded in real NUST/MCS documents instead of the AI just guessing.

---

## The Journey — How This Was Built

This project didn't go in a straight line. Here's the honest story of how it came together:

1. **Started with a different AI provider.** The original plan was to use OpenAI (the company behind ChatGPT) for both answering questions and understanding documents.
2. **Hit a dead end.** The OpenAI key we had turned out to be invalid/broken. Rather than wait, the entire project was switched over to **Mistral AI** — a different AI company that offers similar tools (chat and "embeddings," explained later) at a lower cost.
3. **Took over unfinished work.** Some early groundwork (downloading files, converting them to text) had already been done by an automated tool before it ran out of usage credits. That existing work was reviewed, kept where it was good, and continued from there — instead of starting over from zero.
4. **Found a serious accuracy bug.** Early testing showed that MCS students were sometimes being given information that only applied to the NUST H-12 campus (like hostel details for a hostel they don't even live in). This was traced back to how documents were being labeled, and fixed — see [Problems We Faced and Fixed](#problems-we-faced-and-fixed).
5. **Built a real product around it.** What started as a backend script eventually grew a full chat website: a sign-in system, a chat interface that looks and feels like ChatGPT, voice support, and more.
6. **Got it ready for the real world.** The final stretch was about making sure this could actually go live on the internet reliably and for free — choosing where to host it, and making sure no student's data gets lost or mixed up with another student's.

---

## How It Works, Step by Step

Think of building UniBot's brain like building a library, and then teaching a librarian how to use it.

### Part A — Building the Library (done once, then occasionally updated)

This is the "ingestion pipeline" — a series of scripts that turn raw university PDFs into a searchable knowledge base.

1. **Download** (`download.py`) — Visits the official NUST and MCS "downloads" web pages and grabs every relevant PDF file (handbooks, forms, policies, etc.).
2. **Extract** (`extract.py`) — Opens every PDF and pulls out the plain text, saving it as a Markdown file (a simple text format). Scanned/image-only PDFs (with no real text inside) are skipped.
3. **AI Analysis** (`ai_analyser.py`) — This is the clever part. An AI model reads every single document and decides:
   - Is this actually useful for a new student? (A tender notice or a staff recruitment ad gets thrown out.)
   - Which campus does this apply to — NUST H-12, MCS, or both?
   - What category is it (Admissions, Hostel, Fee Structure, etc.)?
   - A short summary of what it says.

   The AI is specifically told: *MCS and NUST H-12 are different campuses. If a document describes hostel life, facilities, or campus rules that only make sense for H-12, mark it as NOT useful for MCS students.* This is exactly how the campus mix-up bug (mentioned above) was fixed at the root.

4. **Chunking** (`chunk_documents.py`) — Long documents get cut into smaller "chunks" (bite-sized pieces, roughly a paragraph or a section each). This matters because AI models can only "read" a limited amount of text at once, and smaller, focused chunks give more accurate answers than giant walls of text. Chunks are split intelligently — by headings and paragraphs, never in the middle of a sentence.
5. **Embeddings** (`generate_embeddings.py`) — Every chunk of text gets converted into an "embedding" — a list of numbers that represents the *meaning* of that text (not just the words). Two chunks that mean similar things end up with similar numbers, even if they use completely different words. This is what lets the system find "hostel fees" when a student asks about "how much do I pay to live on campus," even though the words don't match exactly.
6. **Upload to Qdrant** (`qdrant_upload.py`) — All these chunks and their embeddings get uploaded into Qdrant, a special kind of database built specifically for searching by "meaning" instead of exact keywords. Think of it as the finished, searchable library shelf.

### Part B — Answering a Student's Question (happens every time someone chats)

1. A student types a question into the chat, e.g., "What documents do I need for MCS admission?"
2. The backend turns that question into an embedding (same trick as above).
3. Qdrant is asked: "Which stored chunks have a similar meaning to this question?" It returns the most relevant handful of chunks — the real paragraphs from real official documents.
4. Those chunks get handed to the Mistral AI chat model along with the question, with an instruction like: *"Answer using ONLY the information below."*
5. The AI writes a natural, human-sounding answer, streaming it back word-by-word (like watching ChatGPT type).
6. The question and answer are saved to that student's own chat history, so they can come back and see it later.

---

## Data Collection and Cleaning

This part took real effort, so it deserves its own section.

### Where the data came from

All source documents were downloaded directly from the **official NUST and MCS websites' "downloads" pages** — real, official PDFs: student handbooks, admission forms, hostel applications, fee forms, academic calendars, codes of conduct, and more.

### Filtering out the junk

Not every PDF on a university website is useful for a chatbot helping new students. Documents were filtered out if they were things like:

- Tenders, vendor quotations, procurement notices
- Staff/employee recruitment ads
- One-off event schedules or sports fixtures
- Research papers or course syllabi (too narrow/technical for a general student assistant)

This filtering happened in two layers: simple keyword rules first (fast, catches the obvious junk), then a smarter AI review for anything less obvious.

### The campus-mixup problem (the big cleaning job)

The most important cleaning job was fixing the **MCS vs NUST H-12 mix-up**. Since MCS and NUST share a website structure and some documents look similar, a batch of documents describing NUST H-12's own hostels, gyms, and campus facilities had been mixed into the knowledge base as if they applied to everyone — including MCS students, for whom that information is simply wrong (they live and study at a different physical location with different facilities).

To fix this properly:

- The AI analysis step (see above) was rewritten to explicitly understand that MCS and NUST H-12 are different physical campuses.
- Every document was re-examined with this new understanding, and anything that was campus-specific to H-12 but not MCS was marked "not useful for MCS."
- On top of the automatic AI review, a manual cleanup pass removed batches of clearly wrong or low-value files (several hundred files were removed in total across a few rounds of cleaning) from the `data/raw/MCS` and `data/raw/NUST` folders.

### A sneaky bug: duplicate filenames

Both the MCS and NUST folders happened to contain some files with the exact same name (for example, both had a file literally called `PAPER-RECHECKING-FORM.md`). The system that assigns a unique ID to each chunk of text was originally based only on the filename — which meant chunks from two *different* documents (one from MCS, one from NUST) could accidentally get the *same* ID and silently overwrite each other in the database. This was fixed by generating IDs from each file's full folder path instead of just its filename, guaranteeing every document gets a truly unique ID.

---

## Problems We Faced and Fixed

A short, honest list of the real bumps hit along the way:

| Problem | What Went Wrong | How It Was Fixed |
|---|---|---|
| Invalid AI key | The original OpenAI API key didn't work | Rebuilt the entire pipeline and backend around Mistral AI instead |
| Wrong campus info | MCS students were shown NUST H-12-only info (hostels, facilities) | Rewrote the AI analysis step to understand the two campuses are different, re-cleaned the data |
| Duplicate chunk IDs | Same filename in two folders caused data to silently overwrite itself in the database | Chunk IDs now include a hash of the full file path, not just the filename |
| Blank screen after email verification | The app kept using an old, outdated login "token" that still said the email wasn't verified yet | Made the app fetch a fresh token right after verifying, and added safety checks so a failed request never crashes the whole screen |
| Chat history stored only on one computer | Using a local file-based database (SQLite) means the data disappears every time the app is redeployed to a hosting service | Migrated chat history storage to a real cloud database (PostgreSQL, hosted on Neon), so it's reliable and available from anywhere |
| Browser auto-filling old login info after refresh | Chrome was silently restoring old typed text into the login form | Adjusted the form fields so the browser can't do this |
| Text looked "too bold" and heavy | Headings in chat replies used a very heavy font weight | Capped the maximum boldness and switched to a cleaner font |

---

## Tech Stack (Tools Used and Why)

| Tool | What It Does | Why We Picked It |
|---|---|---|
| **Python** | The programming language for everything behind the scenes (data pipeline + backend) | Best supported language for AI tools |
| **Mistral AI** | Provides the "brain" — reads documents, understands questions, writes answers, and creates embeddings | Reliable, affordable, and it actually worked (unlike our original OpenAI key) |
| **OpenAI (Whisper + TTS)** | Used *only* for voice features: turning speech into text, and text into speech | Mistral doesn't offer voice tools, so this one feature borrows OpenAI specifically for that |
| **Qdrant** | A "vector database" — a special search engine that finds text by meaning, not just exact words | Purpose-built for exactly this kind of AI search, and has a free cloud tier |
| **FastAPI** | The web framework that powers the backend server (the part that receives chat messages and sends back answers) | Fast, modern, and works very well with real-time streaming responses |
| **PostgreSQL (via Neon)** | Stores every user's chat sessions and messages reliably in the cloud | Doesn't disappear when the app restarts or redeploys, unlike a local file |
| **Firebase Authentication** | Handles user sign-up and login (Google sign-in and email/password) | Trusted, well-tested, and free at this scale |
| **React + Vite** | Builds the actual website/chat interface the student sees and clicks around in | Modern, fast, and great for a smooth, app-like feel |
| **Vercel / Railway / Neon / Qdrant Cloud** | Where the finished project is hosted, all on free tiers | Zero ongoing cost at this project's scale |

---

## Architecture (How the Pieces Fit Together)

```
                     ┌────────────────────┐
                     │   Student's Browser │
                     │   (React chat app)   │
                     └──────────┬───────────┘
                                │  (asks a question,
                                │   logs in via Firebase)
                                ▼
                     ┌────────────────────┐
                     │   FastAPI Backend   │
                     └──────────┬───────────┘
              ┌─────────────────┼─────────────────────┐
              ▼                 ▼                      ▼
     ┌────────────────┐ ┌───────────────┐   ┌────────────────────┐
     │  Firebase Admin │ │  Mistral AI    │   │  Qdrant Cloud       │
     │  (checks who    │ │  (writes the   │   │  (finds the most    │
     │   you are)      │ │   answer)      │   │   relevant chunks   │
     └────────────────┘ └───────────────┘   │   of real documents) │
                                              └────────────────────┘
              ▼
     ┌────────────────────┐
     │  PostgreSQL (Neon)  │
     │  (saves your chat   │
     │   history safely)   │
     └────────────────────┘
```

Separately, and only run occasionally (not every time a student chats), the **ingestion pipeline** turns raw PDFs into the searchable data that lives in Qdrant. See [How It Works](#how-it-works-step-by-step), Part A.

---

## Features

- **Ask anything about NUST or MCS** and get an answer grounded in real official documents.
- **Correctly tells MCS and NUST H-12 apart** — no more wrong hostel/facility info.
- **Sign in with Google, or with email and password.**
- **Real email verification** — signing up with an email you don't own won't get you in. This is checked and enforced on the server, not just hidden by the app's design.
- **Each user has their own private chat history.** One student can never see another student's conversations.
- **Answers stream in live**, word by word, like watching someone type in real time.
- **Voice support** — you can speak your question out loud, and have the answer read back to you.
- **Multiple conversations**, organized by date (Today, Yesterday, Previous 7 Days, Older), just like ChatGPT.

---

## Project Structure (What's in Each Folder)

```
├── data/                  # Downloaded PDFs, extracted text, chunks, embeddings
│                          # (not pushed to GitHub — it's regenerated by the pipeline scripts)
├── utils/
│   └── llm.py             # All the code that talks to Mistral AI (chat + embeddings)
├── download.py            # Step 1: download PDFs from NUST/MCS websites
├── extract.py             # Step 2: convert PDFs into plain text (Markdown)
├── ai_analyser.py         # Step 3: AI decides what's useful and which campus it belongs to
├── chunk_documents.py     # Step 4: split documents into small, searchable chunks
├── generate_embeddings.py # Step 5: turn chunks into embeddings (meaning-numbers)
├── qdrant_upload.py       # Step 6: upload everything into the Qdrant knowledge base
├── test_pipeline.py       # Quick checks that each part of the pipeline is working
├── config.py              # All settings and secret-key loading, in one place
├── requirements.txt       # Python packages needed for the pipeline scripts above
│
├── backend/               # The live chat server (FastAPI)
│   ├── main.py             # Starting point of the backend server
│   ├── routes/             # The actual API endpoints (chat, voice, conversations)
│   ├── services/           # Talks to Mistral, Qdrant, Firebase, and OpenAI (voice)
│   ├── memory/              # Saves and recalls chat history (short-term + long-term)
│   └── requirements.txt    # Python packages needed for the backend
│
└── frontend/               # The chat website itself (React)
    └── src/
        ├── components/      # Login screen, chat window, sidebar, etc.
        └── App.jsx          # Main app logic
```

---

## How to Run This Project on Your Own Computer

### 1. The ingestion pipeline (builds the knowledge base)

```bash
pip install -r requirements.txt
python download.py
python extract.py
python ai_analyser.py
python chunk_documents.py
python generate_embeddings.py
python qdrant_upload.py
```

Each script picks up where the last one left off — if you run it twice, it won't redo work that's already done.

### 2. The backend (the chat server)

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 3. The frontend (the website)

```bash
cd frontend
npm install
npm run dev
```

Then open the link it gives you (usually `http://localhost:5173`) in your browser.

---

## Environment Variables (Secret Keys You Need)

These go in a file named `.env` in the project's main folder (never share this file or upload it anywhere public — it's already excluded from GitHub).

| Variable | What It's For |
|---|---|
| `MISTRAL_API_KEY` | Lets the app talk to Mistral AI (chat + embeddings) |
| `OPENAI_API_KEY` | Used only for voice features (speech-to-text and text-to-speech) |
| `QDRANT_URL` / `QDRANT_API_KEY` | Connects to your Qdrant Cloud knowledge base |
| `DATABASE_URL` | Your Postgres connection string (e.g. from Neon) — stores chat history |
| `FIREBASE_PROJECT_ID` | Your Firebase project's ID |
| `FIREBASE_SERVICE_ACCOUNT_JSON` or `FIREBASE_SERVICE_ACCOUNT_PATH` | Lets the backend verify who's logged in |
| `ALLOWED_ORIGINS` | Which website addresses are allowed to talk to the backend |

The frontend also needs its own `.env` file inside `frontend/` with your `VITE_FIREBASE_*` settings (from your Firebase project settings page).

---

## Deployment Plan (Putting It Online for Free)

The whole project is designed to run on free hosting, forever, at this project's scale (around 100 users):

- **Frontend** → **Vercel** (free)
- **Backend** → **Railway** (free trial credit, no card required to start; originally planned for Render, but Render started requiring a card to deploy even on its free tier)
- **Chat history database** → **Neon** (free Postgres database, more than enough storage and speed for this many users)
- **Knowledge base** → **Qdrant Cloud** (already in use, free tier)

Railway build/start config lives in `nixpacks.toml` at the repo root — it installs `backend/requirements.txt` (not the root `requirements.txt`, which is for the ingestion pipeline only) and runs `uvicorn` bound to Railway's `$PORT`. The frontend needs `VITE_API_URL` set to the deployed Railway backend URL once it's live (frontend and backend are on different domains, so relative `/api/...` calls need an absolute base outside of local dev).

---

## Future Ideas

Things that could be added later, but aren't needed right now:

- Automatically re-running the ingestion pipeline on a schedule, so new PDFs uploaded by the university get picked up without manual work.
- An admin dashboard to see what questions students are asking most.
- Support for more constituent colleges of NUST beyond MCS.

---

*Built for the students of NUST and MCS — so a new student never has to dig through a PDF at 2 AM just to find out what documents they need.*
