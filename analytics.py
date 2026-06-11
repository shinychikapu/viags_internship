"""
Analytics layer: scikit-learn PCA explorer.

Role of this file
-----------------
The function here is pure: it takes the employees DataFrame loaded by
data.load_employees() and returns a small, plot-ready DataFrame plus the
explained-variance metadata. The actual chart drawing lives in plots.py
(`_pca_chart`) so this module stays free of streamlit / plotly imports —
easier to test in a notebook, easier to swap models later.

Why PCA (and not forecasting)
-----------------------------
A single HR snapshot doesn't naturally support attrition prediction or
hires forecasting (only ~1 leaver is labeled in TSN). The analytics layer
is reframed around dimensionality reduction: project the workforce into
2D so the dashboard can answer "what's the variance structure of this
workforce?". scipy.stats hypothesis tests and KMeans clustering can be
layered on later — both reuse the same transformed feature matrix this
function builds, so they're additive, not blocking.

----------------------------------------------------------------------------
What you need to build (in order)
----------------------------------------------------------------------------

TODO 1: Imports
    - pandas as pd
    - numpy as np
    - from sklearn.compose import ColumnTransformer
    - from sklearn.preprocessing import OneHotEncoder, StandardScaler
    - from sklearn.decomposition import PCA

TODO 2: Module-level feature lists
    NUMERIC_FEATURES     = ["age", "tenure_years", "english_point"]
    CATEGORICAL_FEATURES = ["job_title", "contract_type",
                            "english_band", "labor_group"]
    HOVER_COLS           = ["hr_no", "site", "sex", "age",
                            "english_band", "job_title"]
    Keep these at module scope so plots.py can read them when wiring
    up `_pca_chart`'s hover_data without re-listing the columns.

TODO 3: pca_explorer(df) -> tuple[pd.DataFrame, np.ndarray]

    Pipeline:
      1. Drop rows where any feature is NaN — PCA can't handle them and
         imputing english_point would distort the variance structure.
            sub = df.dropna(subset=NUMERIC_FEATURES + CATEGORICAL_FEATURES)
      2. Build the ColumnTransformer:
            ColumnTransformer([
                ("num", StandardScaler(),                       NUMERIC_FEATURES),
                ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
            ])
         StandardScaler centres+scales the numerics so PCA isn't dominated
         by `english_point` (range 0-990) over `age` (range ~20-65).
         OneHotEncoder(handle_unknown="ignore") means a brand-new job_title
         appearing in a future ETL run won't crash the dashboard — the row
         simply contributes zeros for the unseen category.
      3. X = ct.fit_transform(sub)
      4. pca = PCA(n_components=2).fit(X)
         coords = pca.transform(X)
      5. Build the return frame:
            pcs = sub[HOVER_COLS].copy()
            pcs["pc1"] = coords[:, 0]
            pcs["pc2"] = coords[:, 1]
         Also surface age_group so the chart can colour-by it:
            pcs["age_group"] = sub["age_group"].values

    Returns:
        pcs : DataFrame with columns
              [*HOVER_COLS, 'age_group', 'pc1', 'pc2']
              (one row per non-NaN employee)
        evr : pca.explained_variance_ratio_  (np.ndarray, shape (2,))

    `_pca_chart` in plots.py reads `evr` to put the explained-variance
    percentages in the figure subtitle, so the reader knows how much
    information the 2 components actually preserve.

----------------------------------------------------------------------------
How to verify
----------------------------------------------------------------------------
After data.py is in place:

    from data import load_employees
    from analytics import pca_explorer

    df = load_employees()
    pcs, evr = pca_explorer(df)

    print(pcs.shape)          # ~(2400, 9) — slightly less than df because
                              # of the NaN-drop on english_point etc.
    print(pcs[["pc1", "pc2"]].describe())   # roughly centred near 0
    print(evr, evr.sum())     # each in (0, 1); sum < 1 (it's only 2 of N).
                              # Expect something in the 0.15-0.35 ballpark
                              # for the first component.

----------------------------------------------------------------------------
Future analytics notes (out of scope for v1)
----------------------------------------------------------------------------
- scipy.stats hypothesis tests:
    chi-square (sex × work_type, sex × site, age_group × english_band),
    one-way ANOVA (english_point across dep_name),
    Pearson correlation (age vs tenure_years).
    Render as a results table + -log10(p) bar.
- KMeans clustering:
    Reuse the same X matrix from `pca_explorer`; fit
    KMeans(n_clusters=4, n_init=10, random_state=0); colour the PCA
    scatter by cluster label instead of a real demographic.
"""

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.decomposition import PCA

NUMERIC_FEATURES     = ["age", "tenure_years", "english_point"]
CATEGORICAL_FEATURES = ["job_title", "contract_type", "english_band", "labor_group"]
HOVER_COLS           = ["hr_no", "site", "sex", "age", "english_band", "job_title"]

def pca_explorer(df) -> tuple[pd.DataFrame, np.ndarray]:
    sub = df.dropna(subset=NUMERIC_FEATURES + CATEGORICAL_FEATURES)

    ct = ColumnTransformer([
        ("num", StandardScaler(),                       NUMERIC_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
    ])
    X = ct.fit_transform(sub)

    pca = PCA(n_components=2).fit(X)
    coords = pca.transform(X)

    pcs = sub[HOVER_COLS].copy()
    pcs["pc1"] = coords[:, 0]
    pcs["pc2"] = coords[:, 1]
    pcs["age_group"] = sub["age_group"].values

    return pcs, pca.explained_variance_ratio_