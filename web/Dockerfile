FROM python:3.13.5

COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

CMD streamlit run web_main.py