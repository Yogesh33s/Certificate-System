-- 1. Create the local user
CREATE USER luser IDENTIFIED BY 1234;

-- 2. Grant basic privileges to allow login and object creation
GRANT CONNECT, RESOURCE TO luser;

-- 3. (Optional) Allow unlimited storage in the USERS tablespace
ALTER USER luser QUOTA UNLIMITED ON USERS;
