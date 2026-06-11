# import asyncio
#
# import pytest
#
# from app.workers.task_worker import TaskWorker
# from app.models.task import Task, TaskStatus
#
#
# @pytest.mark.asyncio
# async def test_shutdown_stops_consuming_new(session_factory, fake_rabbit):
#     """stop-event -> цикл чтения выходит, новые сообщения не забираются."""
#     worker = TaskWorker(fake_rabbit, worker_id="w1")
#
#     run_task = asyncio.create_task(worker.run())
#     await fake_rabbit.wait_consuming()   # дождались, что итератор очереди запущен
#
#     worker._stop.set()                   # сигнал на graceful-гашение
#     await asyncio.wait_for(run_task, timeout=5.0)
#
#     # после set цикл вышел, новые сообщения, доставленные после, не тронуты
#     fake_rabbit.deliver(_msg("late-task"))
#     await asyncio.sleep(0.1)
#     assert fake_rabbit.unacked_count() == 1   # осталось в очереди, воркер его не взял
#
#
# @pytest.mark.asyncio
# async def test_shutdown_waits_for_inflight(session_factory, fake_rabbit, slow_process):
#     """Уже взятая задача должна доиграть до ack ДО завершения run."""
#     worker = TaskWorker(fake_rabbit, worker_id="w1")
#     worker._process = slow_process       # обработка искусственно растянута
#
#     task_id = await _seed(session_factory, status=TaskStatus.PENDING)
#     run_task = asyncio.create_task(worker.run())
#     fake_rabbit.deliver(_msg(task_id))
#
#     await slow_process.started.wait()    # дождались, что обработка реально стартовала
#     worker._stop.set()                   # гасим ПОСРЕДИ обработки
#
#     await asyncio.wait_for(run_task, timeout=10.0)
#
#     # run не завершился, пока in-flight задача не доиграла
#     async with session_factory() as s:
#         task = await s.get(Task, task_id)
#         assert task.status == TaskStatus.COMPLETED   # доведена до конца, не брошена
#     assert fake_rabbit.is_acked(task_id)             # и подтверждена
#
#
# @pytest.mark.asyncio
# async def test_shutdown_acks_before_exit(session_factory, fake_rabbit, slow_process):
#     """Инвариант ack-после-статуса держится и при гашении посреди работы."""
#     worker = TaskWorker(fake_rabbit, worker_id="w1")
#     worker._process = slow_process
#
#     task_id = await _seed(session_factory, status=TaskStatus.PENDING)
#     run_task = asyncio.create_task(worker.run())
#     fake_rabbit.deliver(_msg(task_id))
#
#     await slow_process.started.wait()
#     worker._stop.set()
#     await asyncio.wait_for(run_task, timeout=10.0)
#
#     # порядок: финальный статус записан, ПОТОМ ack — не наоборот
#     assert fake_rabbit.ack_happened_after_db_write(task_id)
#
#
# @pytest.mark.asyncio
# async def test_shutdown_timeout_does_not_hang(fake_rabbit, hanging_process):
#     """Зависшая in-flight задача не должна вешать graceful-гашение навсегда."""
#     worker = TaskWorker(fake_rabbit, worker_id="w1", task_timeout=1.0)
#     worker._process = hanging_process    # уходит в бесконечное ожидание
#
#     run_task = asyncio.create_task(worker.run())
#     fake_rabbit.deliver(_msg("hang-task"))
#     await hanging_process.started.wait()
#     worker._stop.set()
#
#     # task_timeout рвёт зависшую обработку -> run всё равно завершается
#     await asyncio.wait_for(run_task, timeout=5.0)
#     assert run_task.done()
#
#
# def _msg(task_id: str):
#     import json
#     from tests.fakes import FakeIncomingMessage
#     return FakeIncomingMessage(body=json.dumps({"task_id": task_id}).encode())
#
#
# async def _seed(session_factory, status: TaskStatus) -> str:
#     async with session_factory() as s:
#         task = Task(title="t", status=status)
#         s.add(task)
#         await s.commit()
#         return str(task.id)