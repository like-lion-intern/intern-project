#!/bin/bash

# ==============================================================================
# 🚀 100% 자동 GCP Cloud Run 배포 스크립트
# ==============================================================================

# 에러시 바로 멈춤
set -e

echo "======================================================"
echo "🔧 구글 클라우드(GCP) 배포 자동화 프로세스를 시작합니다"
echo "======================================================"

# 1. gcloud 명령어가 있는지 확인하고 없으면 설치 (Homebrew 기준)
if ! command -v gcloud &> /dev/null
then
    echo "❌ gcloud CLI가 설치되어 있지 않습니다."
    echo "📦 Homebrew를 통해 gcloud를 설치합니다... (이 작업은 1-2분 정도 소요될 수 있습니다)"
    brew install --cask google-cloud-sdk

    echo "✅ 설치가 완료되었습니다."
    echo "⚠️ 터미널을 다시 열거나, 현재 터미널에서 아래 명령을 수동으로 입력해 경로를 갱신해야 할 수 있습니다."
    echo "source \"$(brew --prefix)/Caskroom/google-cloud-sdk/latest/google-cloud-sdk/path.bash.inc\""
    echo "설치를 마친 후, 이 터미널 창을 껐다 켜서 ./deploy.sh 를 다시 실행해주세요!"
    exit 0
else
    echo "✅ gcloud CLI가 이미 설치되어 있습니다."
fi

# 2. 구글 클라우드 로그인 진행
echo ""
echo "🔑 구글 클라우드에 로그인합니다. 브라우저가 열리면 인증을 완료해주세요."
gcloud auth login

# 3. 프로젝트 ID 확인 및 선택
echo ""
echo "📂 보유한 GCP 프로젝트 목록:"
gcloud projects list
echo ""
read -p "배포를 진행할 [PROJECT_ID] 를 입력해주세요 (위 목록의 PROJECT_ID 복사): " GCP_PROJECT_ID
gcloud config set project "$GCP_PROJECT_ID"
echo "✅ $GCP_PROJECT_ID 프로젝트로 설정되었습니다."

# 4. 사용되는 주요 API들을 활성화 (Cloud Build, Cloud Run, Artifact Registry)
echo ""
echo "⚙️  필수 클라우드 API를 활성화하는 중입니다..."
gcloud services enable cloudbuild.googleapis.com run.googleapis.com artifactregistry.googleapis.com

# 5. .env 파일에서 배포에 넣을 중요 환경변수 추출
echo ""
echo "🔍 로컬의 .env 파일에서 환경변수를 로드합니다."
if [ ! -f .env ]; then
    echo "❌ .env 파일이 없습니다! DB 주소와 API키가 들어있는 .env 파일이 필요합니다."
    exit 1
fi

source .env

if [ -z "$DATABASE_URL" ] || [ -z "$DATABASE_URL_SYNC" ] || [ -z "$GOOGLE_API_KEY" ]; then
    echo "❌ .env 파일 내에 필수 변수(DATABASE_URL, DATABASE_URL_SYNC, GOOGLE_API_KEY)가 누락되었습니다."
    exit 1
fi

# 6. 소스코드 Cloud Run 배포!
echo ""
echo "🚀 (!!!) 본격적인 클라우드 소스코드 빌드 및 배포를 시작합니다 (!!!)"
echo "이 과정은 5~10분 정도 걸릴당할 수 있으니 터미널을 끄지 말고 기다려주세요."

gcloud run deploy intern-project \
  --source . \
  --region asia-northeast3 \
  --allow-unauthenticated \
  --memory 4Gi \
  --cpu 2 \
  --set-env-vars="DATABASE_URL=$DATABASE_URL,DATABASE_URL_SYNC=$DATABASE_URL_SYNC,GOOGLE_API_KEY=$GOOGLE_API_KEY"

echo "======================================================"
echo "🎉 모든 배포가 완료되었습니다!"
echo "출력된 Service URL (https://intern-project-...run.app) 을 클릭해 확인해보세요!"
echo "======================================================"
