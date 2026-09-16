import os
import psycopg
from psycopg.types.json import Jsonb
from fastapi import FastAPI, HTTPException
from orchestration import router as orchestration_router
from pydantic import BaseModel

app = FastAPI(title='Learning Fabric API', version='0.3.0')
app.include_router(orchestration_router)

DATABASE_URL = os.environ['DATABASE_URL']


class RequestIn(BaseModel):
    content: dict
    request_type: str = 'original_request'


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'learning-fabric-api'}


@app.get('/db/health')
def db_health():
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT 1')
            cur.fetchone()
    return {'status': 'ok', 'database': 'connected'}


@app.post('/work/claim')
def claim_work(node_id: str):
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT communication_id, request_id, content
                FROM communications
                WHERE receiver_node_id = %s
                  AND message_type = 'work_assignment'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM events e
                      WHERE e.request_id = communications.request_id
                        AND e.node_id = communications.receiver_node_id
                        AND e.event_type = 'work_claimed'
                  )
                ORDER BY created_at
                LIMIT 1
                FOR UPDATE
                """,
                (node_id,)
            )

            assignment = cur.fetchone()

            if not assignment:
                return {
                    'status': 'no_work',
                    'node_id': node_id
                }

            communication_id, request_id, content = assignment

            cur.execute(
                """
                INSERT INTO events
                    (event_type, request_id, node_id, data)
                VALUES (%s, %s, %s, %s)
                RETURNING event_id
                """,
                (
                    'work_claimed',
                    request_id,
                    node_id,
                    Jsonb({
                        'status': 'claimed',
                        'communication_id': str(communication_id)
                    })
                )
            )

            event_id = cur.fetchone()[0]

        conn.commit()

    return {
        'status': 'claimed',
        'node_id': node_id,
        'request_id': str(request_id),
        'communication_id': str(communication_id),
        'event_id': str(event_id),
        'assignment': content
    }


class WorkResult(BaseModel):
    node_id: str
    request_id: str
    status: str
    result: dict = {}


@app.post('/work/result')
def submit_work_result(work: WorkResult):
    if work.status not in ('completed', 'failed'):
        raise HTTPException(
            status_code=400,
            detail="status must be 'completed' or 'failed'"
        )

    event_type = (
        'work_completed'
        if work.status == 'completed'
        else 'work_failed'
    )

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT event_id
                FROM events
                WHERE request_id = %s
                  AND node_id = %s
                  AND event_type = 'work_claimed'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (work.request_id, work.node_id)
            )

            claimed = cur.fetchone()

            if not claimed:
                raise HTTPException(
                    status_code=409,
                    detail='No claimed work found for this node and request'
                )

            parent_event_id = claimed[0]

            cur.execute(
                """
                INSERT INTO events
                    (event_type, request_id, node_id,
                     parent_event_id, data)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING event_id
                """,
                (
                    event_type,
                    work.request_id,
                    work.node_id,
                    parent_event_id,
                    Jsonb({
                        'status': work.status,
                        'result': work.result
                    })
                )
            )

            event_id = cur.fetchone()[0]

        conn.commit()

    return {
        'status': work.status,
        'request_id': work.request_id,
        'node_id': work.node_id,
        'event_id': str(event_id),
        'parent_event_id': str(parent_event_id)
    }


@app.post('/nodes/heartbeat')
def node_heartbeat(node_id: str):
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE nodes
                SET status = 'available',
                    last_seen_at = now()
                WHERE node_id = %s
                RETURNING node_id, status, last_seen_at
                """,
                (node_id,)
            )

            node = cur.fetchone()

            if not node:
                raise HTTPException(
                    status_code=404,
                    detail='Node not found'
                )

        conn.commit()

    return {
        'status': 'ok',
        'node_id': str(node[0]),
        'node_status': node[1],
        'last_seen_at': node[2].isoformat()
    }


@app.post('/requests')
def create_request(request: RequestIn):
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:

            cur.execute(
                '''
                SELECT authority_id
                FROM authority
                WHERE name = 'Primary Human Authority'
                  AND active = TRUE
                  AND authority_level = 100
                LIMIT 1
                '''
            )
            authority = cur.fetchone()

            if not authority:
                raise HTTPException(
                    status_code=403,
                    detail='Primary Human Authority not available'
                )

            authority_id = authority[0]

            cur.execute(
                '''
                INSERT INTO requests
                    (authority_id, request_type, content)
                VALUES (%s, %s, %s)
                RETURNING request_id
                ''',
                (
                    authority_id,
                    request.request_type,
                    Jsonb(request.content)
                )
            )
            request_id = cur.fetchone()[0]

            cur.execute(
                '''
                INSERT INTO events
                    (event_type, request_id, data)
                VALUES (%s, %s, %s)
                RETURNING event_id
                ''',
                (
                    'request_received',
                    request_id,
                    Jsonb({
                        'source': 'Primary Human Authority',
                        'status': 'received'
                    })
                )
            )
            event_id = cur.fetchone()[0]

            cur.execute(
                '''
                SELECT node_id
                FROM nodes
                WHERE node_type = 'ai_assistant'
                  AND status = 'available'
                ORDER BY created_at
                LIMIT 1
                '''
            )
            node = cur.fetchone()

            assignment_id = None

            if node:
                node_id = node[0]

                cur.execute(
                    '''
                    INSERT INTO communications
                        (request_id, sender_node_id, receiver_node_id,
                         message_type, content)
                    VALUES (%s, NULL, %s, %s, %s)
                    RETURNING communication_id
                    ''',
                    (
                        request_id,
                        node_id,
                        'work_assignment',
                        Jsonb({
                            'status': 'assigned',
                            'role': 'analysis_and_execution'
                        })
                    )
                )
                assignment_id = cur.fetchone()[0]

                cur.execute(
                    '''
                    INSERT INTO events
                        (event_type, request_id, node_id, data)
                    VALUES (%s, %s, %s, %s)
                    RETURNING event_id
                    ''',
                    (
                        'work_assigned',
                        request_id,
                        node_id,
                        Jsonb({
                            'status': 'assigned',
                            'role': 'analysis_and_execution'
                        })
                    )
                )
                assignment_event_id = cur.fetchone()[0]
            else:
                assignment_event_id = None

        conn.commit()

    return {
        'status': 'accepted',
        'request_id': str(request_id),
        'event_id': str(event_id),
        'assignment_id': str(assignment_id) if assignment_id else None,
        'assignment_event_id': (
            str(assignment_event_id) if assignment_event_id else None
        )
    }
