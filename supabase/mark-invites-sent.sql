-- One-off: the bookings imported from the spreadsheets already had their Outlook invites sent,
-- so mark them as sent. This clears the "Send Outlook invite" checks and the "Invite not sent" flags.
-- Lunches booked in the planner afterwards are still flagged until their invite is marked as sent.
update public.docs
   set updated_at = now(), data = data || '{"inviteSentAt": "before import"}'::jsonb
 where collection = 'lunches'
   and data->>'status' in ('Booked', 'Confirmed')
   and coalesce(data->>'inviteSentAt', '') = '';
