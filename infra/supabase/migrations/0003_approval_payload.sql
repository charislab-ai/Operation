-- CharisLab AI OS — 승인 카드 원본 내용 저장 (텔레그램 확인 메시지를 한 메시지로 합치기 위함)

alter table approvals add column payload jsonb;
