# Tutorials  
  
Real workflows, not toy examples.  
  
## 1. Your first model in 5 minutes  
  
Model a coffee shop's daily revenue based on foot traffic:  
  
```python  
from axiomize import Model  
  
m = Model("coffee-shop")  
m.param("customers_per_day", unit="people", range=(50, 500))  
m.param("avg_spend", unit="USD", range=(3, 15))  
m.equation("revenue = customers_per_day * avg_spend")  
m.simulate(days=30)  
```  
  
## 2. Sensitivity analysis  
  
Which parameter matters more? Find out:  
  
```python  
m.sensitivity(method="sobol", samples=1000)  
```  
  
## 3. Export for your paper  
  
```python  
m.export("report.tex", format="latex")  
```  
  
Full equations, units, and provenance included. Reviewers can check your work. 
