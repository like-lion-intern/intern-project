#!/bin/bash
echo "🚀 Cloud Run 인공지능 서버를 '시작(공개)' 상태로 켭니다..."

# 외부(인터넷) 누구나 다시 접속할 수 있도록 접속 권한(allUsers)을 허용합니다.
gcloud run services add-iam-policy-binding intern-project \
  --region asia-northeast1 \
  --member="allUsers" \
  --role="roles/run.invoker" \
  --quiet

echo "✅ 서버가 켜졌습니다! 이제 사용자들이 인터넷 링크(도메인)로 다시 정상 접속할 수 있습니다."
