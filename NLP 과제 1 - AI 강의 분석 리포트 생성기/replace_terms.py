import os

def replace_technical_terms(text, term_dict):
    """
    텍스트 내의 잘못 인식된 용어들을 사전을 기반으로 일괄 치환하고,
    치환된 내역(어떤 단어가 몇 번 바뀌었는지)을 반환합니다.
    """
    changes = [] # (wrong_term, correct_term, count)
    
    for correct_term, wrong_terms in term_dict.items():
        if isinstance(wrong_terms, (list, tuple)):
            for wrong_term in wrong_terms:
                count = text.count(wrong_term)
                if count > 0:
                    text = text.replace(wrong_term, correct_term)
                    changes.append((wrong_term, correct_term, count))
        else:
            # 단일 문자열인 경우 호환성 유지
            count = text.count(wrong_terms)
            if count > 0:
                text = text.replace(wrong_terms, correct_term)
                changes.append((wrong_terms, correct_term, count))
                
    return text, changes

def process_term_replacement(input_dir, output_dir, term_dict):
    """
    입력 폴더의 텍스트 파일들을 읽어 용어 치환을 수행하고 출력 폴더에 저장합니다.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    total_changes_summary = {} # { filename: [(wrong, correct, count), ...]}

    # 폴더 내의 모든 txt 파일 처리
    for filename in os.listdir(input_dir):
        if not filename.endswith('.txt'):
            continue
            
        input_path = os.path.join(input_dir, filename)
        output_path = os.path.join(output_dir, filename)
        
        # 파일 읽기
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # 용어 치환 
        processed_content, file_changes = replace_technical_terms(content, term_dict)
        
        # 치환된 결과 저장
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(processed_content)
            
        if file_changes:
            total_changes_summary[filename] = file_changes
            print(f"✅ 용어 교정 완료: {filename} ({sum(c[2] for c in file_changes)}건 변경)")
        else:
            print(f"✅ 용어 교정 완료: {filename} (변경 없음)")

    # 상세 결과 출력
    if total_changes_summary:
        print("\n" + "="*50)
        print("📊 파일별 용어 교정 상세 내역")
        print("="*50)
        total_replaced_count = 0
        for filename, changes in total_changes_summary.items():
            print(f"\n📁 {filename}")
            file_total = 0
            for wrong, correct, count in changes:
                print(f"  - '{wrong}' -> '{correct}' ({count}회)")
                file_total += count
            print(f"  총 {file_total}건 변경")
            total_replaced_count += file_total
        
        print("\n" + "="*50)
        print(f"💎 요약: 총 {len(total_changes_summary)}개 파일에서 전체 {total_replaced_count}건의 용어가 교정되었습니다.")
        print("="*50)
    else:
        print("\n교정된 용어가 없습니다.")

if __name__ == "__main__":
    # =============== 사용 설정 ===============
    # 1차 전처리가 완료된 파일들이 위치한 폴더
    INPUT_FOLDER = r"c:\Users\changhyun\Desktop\likelion_internship\NLP 과제 1 - AI 강의 분석 리포트 생성기\강의 스크립트_1차_전처리완료"
    
    # 2차 전처리(용어 교정)가 완료된 파일을 저장할 새 폴더 경로 (자동 생성됨)
    OUTPUT_FOLDER = r"c:\Users\changhyun\Desktop\likelion_internship\NLP 과제 1 - AI 강의 분석 리포트 생성기\강의 스크립트_2차_용어교정완료"
    
    # 교정할 용어 사전 (올바른 단어: (잘못된 단어1, 잘못된 단어2, ...))
    # 여러 가지로 잘못 인식된 형태를 리스트나 튜플로 모아둡니다.
    JAVA_TERM_DICT = {
        "MySQL": ("마이에스q엘", "마S큐L", "마이에스큐엘", "마이로스큐엘"),
        "Java IO": ("자바 아이오", "잡아이오", "자바 아이요", "j잡아 이오"),
        "Java NIO": ("자바 NIO", "자바 엔아이오", "자반 NIO"),
        "NIO": ("엔아이오", "앤아이오"),
        "Stream API": ("스트림 API", "스트림 에이피아이", "스티림 에이피아이"),
        "ObjectInputStream": ("오브젝트 인풋 스트림", "오브젝트 인푸 스트림"),
        "ObjectOutputStream": ("오브젝트 아웃풋 스트림", "오브젝 아웃풋 스트림"),
        "BufferedReader": ("버퍼드 리더", "버퍼 드리더"),
        "FileWriter": ("파이라이터", "파일라이터"),
        "FileInputStream": ("파일 인풋 스트림", "파이 인풋 스트림"),
        "transient": ("트랜지언트", "트랜시언트", "트렌지언트"),
        "Serializable": ("시리얼라이저블", "시리얼 라이저블"),
        "class": ("클래스", "클라스"),
        "JDK": ("제이디케이", "제이디 K"),
        "Collection": ("컬렉션", "콜렉션"),
        "Framework": ("프리임워크", "프레임워크", "프레임웍"),
        # 새로운 올바른 단어가 생기면 여기에 추가: ("오타1", "오타2")
    }
    # ==========================================
    
    print(f"🚀 IT 전문 용어 교정(2단계) 파이프라인 시작...\n")
    print(f"- 입력 폴더: {INPUT_FOLDER}")
    print(f"- 교정 단어 수: {len(JAVA_TERM_DICT)}개\n")
    
    process_term_replacement(INPUT_FOLDER, OUTPUT_FOLDER, JAVA_TERM_DICT)
    
    print("\n🎉 모든 파일의 용어 교정 작업이 완료되었습니다!")
