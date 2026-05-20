-- vw_CoffeePostsFlat
--
-- Mirrors the flat shape produced by scripts/flatten_posts.py
-- (one row per question, one row per answer; question fields like
-- ViewCount/AnswerCount stay NULL on answer rows; Title and Tags are
-- denormalized onto answer rows).
--
-- Tags is emitted as a comma-separated string so the Azure AI Search
-- SQL indexer can ingest it via the `Collection(Edm.String)` mapping
-- using `delimitedText` or a JSON parser. Switch to STRING_AGG ... ','
-- if you prefer a different delimiter.
--
-- LastActivityDateHWM is a non-null DATETIME2 suitable for the indexer's
-- high-water-mark change-detection policy. Answers don't track
-- LastActivityDate in the dump, so we fall back to CreationDate.

IF OBJECT_ID('dbo.vw_CoffeePostsFlat', 'V') IS NOT NULL
    DROP VIEW dbo.vw_CoffeePostsFlat;
GO

CREATE VIEW dbo.vw_CoffeePostsFlat AS
WITH PostTagAgg AS (
    SELECT
        pt.PostId,
        STRING_AGG(pt.TagName, ',') WITHIN GROUP (ORDER BY pt.TagName) AS Tags
    FROM dbo.PostTags pt
    GROUP BY pt.PostId
)
SELECT
    CONCAT('q-', p.Id)                                   AS id,
    CAST('question' AS NVARCHAR(10))                     AS kind,
    p.Id                                                 AS questionId,
    p.Title                                              AS title,
    p.Body                                               AS body,
    pta.Tags                                             AS tags,
    p.Score                                              AS score,
    CAST(NULL AS INT)                                    AS parentScore,
    p.ViewCount                                          AS viewCount,
    p.AnswerCount                                        AS answerCount,
    p.AcceptedAnswerId                                   AS acceptedAnswerId,
    CAST(0 AS BIT)                                       AS isAccepted,
    p.CommentCount                                       AS commentCount,
    p.CreationDate                                       AS creationDate,
    p.LastActivityDate                                   AS lastActivityDate,
    p.OwnerUserId                                        AS ownerUserId,
    COALESCE(u.DisplayName, p.OwnerDisplayName)          AS ownerDisplayName,
    CONCAT('https://coffee.stackexchange.com/questions/', p.Id) AS url,
    LTRIM(RTRIM(CONCAT(p.Title, CHAR(10), CHAR(10), p.Body))) AS chunk,
    COALESCE(p.LastActivityDate, p.CreationDate)         AS LastActivityDateHWM
FROM dbo.Posts p
LEFT JOIN dbo.Users u ON u.Id = p.OwnerUserId
LEFT JOIN PostTagAgg pta ON pta.PostId = p.Id
WHERE p.PostTypeId = 1

UNION ALL

SELECT
    CONCAT('a-', a.Id)                                   AS id,
    CAST('answer' AS NVARCHAR(10))                       AS kind,
    a.ParentId                                           AS questionId,
    q.Title                                              AS title,
    a.Body                                               AS body,
    pta.Tags                                             AS tags,           -- inherited from parent question
    a.Score                                              AS score,
    q.Score                                              AS parentScore,
    CAST(NULL AS INT)                                    AS viewCount,
    CAST(NULL AS INT)                                    AS answerCount,
    CAST(NULL AS INT)                                    AS acceptedAnswerId,
    CASE WHEN q.AcceptedAnswerId = a.Id THEN CAST(1 AS BIT) ELSE CAST(0 AS BIT) END AS isAccepted,
    a.CommentCount                                       AS commentCount,
    a.CreationDate                                       AS creationDate,
    a.CreationDate                                       AS lastActivityDate,
    a.OwnerUserId                                        AS ownerUserId,
    COALESCE(u.DisplayName, a.OwnerDisplayName)          AS ownerDisplayName,
    CONCAT('https://coffee.stackexchange.com/a/', a.Id)  AS url,
    LTRIM(RTRIM(CONCAT('Q: ', q.Title, CHAR(10), CHAR(10), 'A: ', a.Body))) AS chunk,
    a.CreationDate                                       AS LastActivityDateHWM
FROM dbo.Posts a
JOIN dbo.Posts q       ON q.Id = a.ParentId
LEFT JOIN dbo.Users u  ON u.Id = a.OwnerUserId
LEFT JOIN PostTagAgg pta ON pta.PostId = a.ParentId
WHERE a.PostTypeId = 2;
GO
