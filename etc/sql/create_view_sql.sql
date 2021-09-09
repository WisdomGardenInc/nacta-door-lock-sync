CREATE OR REPLACE VIEW vw_door_lock_record
AS
SELECT
  dlr.`id` AS id,
  dlr.`name` AS user_name,
  dlr.`access_at`,
  dlr.`access`,
  cs.`name` AS room_name,
  cl.`name` AS building_name,
  dlr.`access_way`,
  dlr.`card_no`
FROM door_lock_record dlr
LEFT JOIN core_space cs ON dlr.space_id = cs.id
LEFT JOIN core_location_space cls ON cs.id = cls.space_id
LEFT JOIN core_location cl  ON cls.location_id = cl.id
ORDER BY dlr.access_at DESC;