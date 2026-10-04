import sys

def search_file(filename, keyword):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if keyword in line:
                    print(f"{i+1}: {line.strip()}")
    except UnicodeDecodeError:
        with open(filename, 'r', encoding='cp949') as f:
            for i, line in enumerate(f):
                if keyword in line:
                    print(f"{i+1}: {line.strip()}")

search_file('streamlit_app.py', '개체이력번호')
search_file('streamlit_app.py', '출하성적 추출')
search_file('streamlit_app.py', '1단계')
