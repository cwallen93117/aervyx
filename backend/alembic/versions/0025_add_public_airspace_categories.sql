ALTER TABLE site_settings
  ADD COLUMN IF NOT EXISTS public_airspace_categories_json JSON;

UPDATE site_settings
SET public_airspace_categories_json = '["B", "C", "D", "P", "R", "W", "A", "MOA", "TFR"]'
WHERE id = 1 AND public_airspace_categories_json IS NULL;
