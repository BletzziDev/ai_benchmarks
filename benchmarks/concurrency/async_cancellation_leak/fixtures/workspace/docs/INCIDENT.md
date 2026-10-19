# OPS-2207 — export workers stall; some exports run twice

- After a few hours, the export service stops making progress: all workers wait for a database
  connection, but the database shows no open sessions from the service. Pool metrics show
  `available` drifting down after each deploy and after every burst of client-side cancellations
  (users closing the export dialog cancels the job task). Restarting restores capacity.
- Some customers received the same export twice. The queue is at-least-once and redelivers a
  message if it is not acknowledged within 30 s; long exports are routinely redelivered while still
  running.
- During deploys, `shutdown(grace=20)` returns, the process is told to exit, and the logs still show
  export jobs writing for a while afterwards (and sometimes "Task was destroyed but it is pending!").
