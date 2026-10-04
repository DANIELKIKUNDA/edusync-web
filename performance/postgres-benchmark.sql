-- Point 10H6: execute after setting a real tenant id and ANALYZE on production-like data.
-- psql: \set school_id '00000000-0000-0000-0000-000000000000'
SET LOCAL app.school_id = :'school_id';
EXPLAIN (ANALYZE,BUFFERS) SELECT school_id,status,count(*) FROM students WHERE school_id=:'school_id'::uuid GROUP BY school_id,status;
EXPLAIN (ANALYZE,BUFFERS) SELECT s.id,s.matricule,s.last_name,s.middle_name,s.first_name FROM students s WHERE s.school_id=:'school_id'::uuid AND s.last_name ILIKE '%ka%' ORDER BY s.last_name,s.middle_name,s.first_name LIMIT 100;
EXPLAIN (ANALYZE,BUFFERS) SELECT e.id,e.student_id,e.class_id,e.status FROM enrollments e WHERE e.school_id=:'school_id'::uuid AND e.academic_year_id=:'year_id'::uuid AND e.status<>'CANCELLED' ORDER BY e.enrolled_on DESC LIMIT 100;
EXPLAIN (ANALYZE,BUFFERS) SELECT * FROM finance_payments WHERE school_id=:'school_id'::uuid ORDER BY created_at DESC LIMIT 100;
EXPLAIN (ANALYZE,BUFFERS) SELECT * FROM outbox_events WHERE school_id=:'school_id'::uuid AND published_at IS NULL ORDER BY created_at LIMIT 100;
EXPLAIN (ANALYZE,BUFFERS) SELECT * FROM audit_events WHERE school_id=:'school_id'::uuid ORDER BY occurred_at DESC LIMIT 200;
EXPLAIN (ANALYZE,BUFFERS) SELECT * FROM inventory_item_movements WHERE school_id=:'school_id'::uuid AND item_id=:'item_id'::uuid ORDER BY created_at DESC LIMIT 200;
