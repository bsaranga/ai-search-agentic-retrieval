-- Re-shape vw_CoffeePostsFlat so the Azure AI Search SQL indexer can
-- ingest it without custom transforms:
--   * IDs cast to NVARCHAR (matches Edm.String in the index)
--   * tags emitted as a JSON array string for `jsonArrayToStringCollection`
--   * LastActivityDateHWM stays as the high-water-mark column

IF OBJECT_ID('dbo.vw_CoffeePostsFlat', 'V') IS NOT NULL
    DROP VIEW dbo.vw_CoffeePostsFlat;
GO

CREATE VIEW dbo.vw_CoffeePostsFlat AS
WITH PostTagAgg AS (
    SELECT
        pt.PostId,
        CONCAT(
            '[',
            STRING_AGG('"' + STRING_ESCAPE(pt.TagName, 'json') + '"', ',')
                WITHIN GROUP (ORDER BY pt.TagName),
            ']'
        ) AS TagsJson
    FROM dbo.PostTags pt
    GROUP BY pt.PostId
)
SELECT
    CONCAT('q-', p.Id)                                   AS id,
    CAST('question' AS NVARCHAR(10))                     AS kind,
    CAST(p.Id AS NVARCHAR(20))                           AS questionId,
    p.Title                                              AS title,
    p.Body                                               AS body,
    COALESCE(pta.TagsJson, '[]')                         AS tags,
    p.Score                                              AS score,
    CAST(NULL AS INT)                                    AS parentScore,
    p.ViewCount                                          AS viewCount,
    p.AnswerCount                                        AS answerCount,
    CAST(p.AcceptedAnswerId AS NVARCHAR(20))             AS acceptedAnswerId,
    CAST(0 AS BIT)                                       AS isAccepted,
    p.CommentCount                                       AS commentCount,
    p.CreationDate                                       AS creationDate,
    p.LastActivityDate                                   AS lastActivityDate,
    CAST(p.OwnerUserId AS NVARCHAR(20))                  AS ownerUserId,
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
    CAST(a.ParentId AS NVARCHAR(20))                     AS questionId,
    q.Title                                              AS title,
    a.Body                                               AS body,
    COALESCE(pta.TagsJson, '[]')                         AS tags,
    a.Score                                              AS score,
    q.Score                                              AS parentScore,
    CAST(NULL AS INT)                                    AS viewCount,
    CAST(NULL AS INT)                                    AS answerCount,
    CAST(NULL AS NVARCHAR(20))                           AS acceptedAnswerId,
    CASE WHEN q.AcceptedAnswerId = a.Id THEN CAST(1 AS BIT) ELSE CAST(0 AS BIT) END AS isAccepted,
    a.CommentCount                                       AS commentCount,
    a.CreationDate                                       AS creationDate,
    a.CreationDate                                       AS lastActivityDate,
    CAST(a.OwnerUserId AS NVARCHAR(20))                  AS ownerUserId,
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
