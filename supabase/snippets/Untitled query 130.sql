DELETE FROM job
WHERE NULLIF(description_plain, '') IS NULL;
