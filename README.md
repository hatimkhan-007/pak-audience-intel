# Pakistan Social Audience & Campaign Intelligence Engine

A clustering-based social media analytics project focused on
understanding audience behaviour and discovering actionable marketing
opportunities for Pakistani brands.

## Overview

Pakistani brands use platforms such as Instagram, TikTok, and Facebook
to promote products and seasonal campaigns. These campaigns generate
large volumes of comments and engagement data, but extracting useful
patterns from this information can be difficult.

The **Pakistan Social Audience & Campaign Intelligence Engine** aims to
turn social media post and comment data into meaningful audience
segments, unusual-pattern insights, and evidence-based marketing
recommendations.

The project focuses on **audience segmentation and campaign
intelligence**, rather than simply classifying comments as positive or
negative.

## Problem Statement

A fashion brand running an Eid, 11.11, or 12.12 campaign may receive
comments such as:

-   "Price please?"
-   "Is this available in Karachi?"
-   "Price bohat zyada hai."
-   "Delivery kitne din mein hogi?"
-   "Any discount on this suit?"
-   "Ordered last week, still waiting."

Although these comments reveal customer needs and concerns, those
patterns may remain hidden when thousands of interactions are reviewed
manually.

This project will analyse available post-level engagement data and
associated comments to help answer:

1.  Which types of content attract the most attention?
2.  What are audiences asking for or concerned about?
3.  Which posts show unusual engagement or comment patterns?
4.  What audience-need segments can be identified?
5.  What practical actions should the marketing team consider next?

## Project Objectives

-   Organise social media post, campaign, engagement, and comment data.
-   Discover groups of similar audience behaviours using clustering.
-   Identify recurring topics such as price, quality, sizing, delivery,
    discounts, availability, and purchase interest.
-   Compare engagement across content types and campaigns.
-   Flag posts with patterns that differ substantially from comparable
    posts.
-   Produce understandable, data-supported marketing recommendations.

## Core Features

### 1. Content Performance Analysis

Compare content formats such as:

-   Reels
-   Product photographs
-   Influencer posts
-   Styling videos
-   Sale announcements
-   Eid campaign posts

Analyse available engagement measures, including likes, comments,
shares, and views.

### 2. Audience Need Discovery

Explore comment patterns around topics such as:

-   Price inquiries
-   Fabric and product quality
-   Size and fitting
-   Delivery questions or complaints
-   Discount requests
-   Product availability
-   Purchase interest

Comments may contain English, Urdu, and Roman Urdu. Language information
should be retained where available.

### 3. Audience Segmentation Through Clustering

Group similar audience interactions or behaviour patterns into
interpretable segments. Possible segment examples include:

-   Discount-focused shoppers
-   Delivery-concerned customers
-   Product-availability inquiries
-   Price-sensitive audiences
-   Customers showing purchase interest

These are examples of segments to investigate, not predetermined
findings. Final segment labels should be based on the actual clustering
results and their interpretation.

### 4. Unusual Pattern Detection

Highlight posts whose engagement levels or comment patterns differ
substantially from comparable posts. These posts can then be reviewed
for possible campaign, content, or customer-service insights.

### 5. Marketing Recommendations

Translate analytical findings into practical suggestions for:

-   Content strategy
-   Promotions and discounts
-   Customer-service priorities
-   Product information and availability communication
-   Future campaign experiments

Recommendations should be linked to observed data rather than presented
as unsupported assumptions.

## Initial Dataset Scope

The initial demonstration will focus on **one product category, such as
women's lawn suits**, to keep the project manageable.

The project brief proposes approximately **2,000--5,000 public post
records and associated comments**, subject to suitable data access and
permissions. The dataset can be expanded if reliable data sources become
available.

### Social Media Posts

  Field                Description                            Example
  -------------------- -------------------------------------- ------------------
  `post_id`            Unique post identifier                 `P001`
  `brand`              Brand name or anonymised brand label   `Brand A`
  `platform`           Social media platform                  `Instagram`
  `campaign`           Campaign name                          `Eid Collection`
  `content_type`       Format of the post                     `Reel`
  `product_category`   Product category                       `Lawn suit`
  `likes`              Number of likes                        `1250`
  `comments_count`     Number of comments                     `186`
  `shares`             Number of shares, if available         `95`
  `views`              Number of views, if available          `25000`
  `days_since_post`    Age of the post in days                `5`

### Social Media Comments

  -----------------------------------------------------------------------
  Field                   Description             Example
  ----------------------- ----------------------- -----------------------
  `post_id`               ID of the related post  `P001`

  `comment_text`          Original comment text   `Price please?`

  `language_type`         Detected or recorded    `English`
                          language                

  `topic`                 Identified comment      `Price inquiry`
                          topic                   

  `sentiment`             Sentiment label, if     `Neutral`
                          included                

  `purchase_intent`       Indication of possible  `Possible inquiry`
                          purchase interest       
  -----------------------------------------------------------------------

The examples above are illustrative and are not actual measurements from
the named brands.

## Potential Data Sources

The project brief identifies the following starting points.
Availability, access conditions, and reuse permissions must be checked
before use.

-   **Pakistani fashion brand research:** A 2026 paper, *Sentiment
    Analysis of Social Media Data for Pakistani Fashion Brand Monitoring
    Using Machine Learning*, describes 10,602 observations involving 17
    Pakistani fashion brands across seven platforms. Check the paper and
    accompanying materials for dataset and code availability.\
    https://www.thesesjournal.com/index.php/1/article/view/3247

-   **Open Data Pakistan e-commerce dataset:** Approximately half a
    million historical order records are listed, including order status,
    category, payment method, and customer identifiers. This is
    transaction data, not a social-media comments dataset, and may be
    useful only as an additional source of business context.\
    https://opendata.com.pk/dataset/pakistan-largest-ecommerce-dataset

-   **Pakistani Fashion Catalogue:** A dataset of 75 product records
    from five Pakistani retailers, including product categories and PKR
    prices. It can provide product context but cannot replace
    audience-engagement data.\
    https://huggingface.co/datasets/Osama-Ansar/pakistani-fashion-catalogue

Potential brands to examine include Sapphire, Khaadi, and Gul Ahmed,
subject to platform access rules and permitted data use.

## Proposed Analysis Workflow

1.  **Data collection:** Gather permitted post records, engagement
    metrics, and associated comments.
2.  **Data preparation:** Remove duplicates, handle missing values,
    standardise fields, and preserve original comment text.
3.  **Text preparation:** Prepare English, Urdu, and Roman Urdu comments
    for analysis while retaining language information.
4.  **Feature engineering:** Create useful comment-level and post-level
    features for audience and campaign analysis.
5.  **Exploratory analysis:** Examine engagement distributions, content
    formats, campaign performance, and common audience needs.
6.  **Clustering:** Apply suitable clustering methods to discover groups
    of similar audience behaviours.
7.  **Pattern investigation:** Identify unusual post-level engagement or
    comment patterns for further review.
8.  **Interpretation:** Explain the discovered segments and patterns in
    understandable terms.
9.  **Recommendations:** Generate marketing suggestions supported by the
    analysis.
10. **Presentation:** Display findings through a small web application
    or analytical dashboard.

## Expected Output

The completed system is intended to provide:

-   Content-performance comparisons.
-   Summaries of recurring audience needs.
-   Interpretable audience clusters.
-   Posts flagged for unusual patterns.
-   Evidence-based marketing recommendations.
-   Visual summaries that help a marketing team explore the findings.

## Responsible Data Use

-   Use permitted data-access methods and follow each platform's terms
    of service.
-   Do not assume that all comments or analytics are publicly
    downloadable.
-   Check dataset licences and reuse permissions before using or
    redistributing data.
-   Record source URLs, collection dates, data provenance, and
    applicable permissions for research datasets.
-   Clearly distinguish real observations from generated or simulated
    records.
-   Avoid exposing personal or sensitive information in reports and
    demonstrations.

## Project Status

**Status:** Planning / development

The project scope and initial data structure are defined. Dataset
preparation, clustering experiments, pattern analysis, and the
application interface are planned implementation steps.

## Future Enhancements

-   Expand beyond the initial fashion product category.
-   Add more brands and social media platforms where permitted data is
    available.
-   Improve multilingual handling for Urdu and Roman Urdu.
-   Compare clustering approaches and evaluate cluster quality.
-   Add campaign-level comparisons and richer visualisations.
-   Incorporate additional product or transaction context where
    appropriate.

------------------------------------------------------------------------

*This project is developed for academic and educational purposes as a
Big Data Analytics project.*
