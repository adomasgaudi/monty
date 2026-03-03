import pandas as pd

url = "https://rankings.officialstreetlifting.com/competitions/fnsl-pull-only-2025"
df_list = pd.read_html(url)  # pulls all HTML tables
# often the first or second df contains the results
pull_df = df_list[0]  # adjust index if needed
pull_df = pull_df[['Athlete', 'Pull (kg)']]
pull_df.to_csv("pull_only_2025.csv", index=False)