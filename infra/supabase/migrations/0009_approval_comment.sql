-- 보완(revision) 요청 시 CEO가 텔레그램에서 카드에 "답장(reply)"으로 사유를 입력할 수 있게 함.
-- 버튼 클릭만으로는 자유 텍스트를 받을 수 없어, 보완 버튼을 누르면 이 플래그를 세우고
-- 카드에 답장으로 온 다음 메시지를 그 사유로 매칭한다(app/api/telegram.py 참고).
alter table approvals add column awaiting_comment boolean not null default false;
