# 05-05-2026
### Outlier detection
It's Tuesday, just after the Data Science Team Meeting. I presented my outlier detection work `C:\Users\s223850\UTSW_Projects\Sepsis-Analysis\OutlierDetection.pptx` and we agreed on the following:
1. Keep layer one applied on the vitals
2. Move layer 2 and 3 to the extracted features SIRS score, and Sepsis severity score to detect fast changes in score and statistically outliers
3. Design how to build the 3-layers outlier detection in a way to encorporate each layer independently in a separate places in the data pipeline
4. Integrate the outlier detection algorithm to the data pipeline and place the layers acccordingly
5. Stitch the analysis module to the data pipeline and **make sure to compare between prior and after the outlier detection pipeline**
