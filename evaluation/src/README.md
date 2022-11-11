# Evaluation of Flex algorithm results
This script contains

## Installation
Python 3.9 with requirements installed

```bash
pip install -r requirements.txt
```

## How to use
In order to evaluate you need two .csv files, one with the true measurements of the plants and another with
the predicted measurements.

### True measurements CSV columns

* `rc_visard_id` (string) : represents the serial number of the rc_visard device used to aquire data with. (Roots: 07010541, TomatoWorld: 06784657)
* `date` (datetime) : TODO: add description
* `plant_number` () : TODO: add description
* `path_number` () : TODO: add description
* `leaf_length` () : TODO: add description
* `leaf_width` () : TODO: add description
* `head_length` () : TODO: add description
* `head_width` () : TODO: add description
* `tomato_setting_truss_number` () : TODO: add description
* `tomato_setting` () : TODO: add description
* `flower_setting_truss_number` () : TODO: add description
* `flower_setting` () : TODO: add description

### Predicted measurements CSV columns

* `rc_visard_id` (string) : represents the serial number of the rc_visard device used to aquire data with. (Roots: 07010541, TomatoWorld: 06784657)
* `date` (datetime) : TODO: add description
* `plant_number` () : TODO: add description
* `path_number` () : TODO: add description
* `circumference` () : TODO: add description
* `leaf_area` () : TODO: add description
* `length` () : TODO: add description
* `width` () : TODO: add description
* `tomato_setting` () : TODO: add description
* `flower_setting` () : TODO: add description
* `stem_color_R` () : TODO: add description
* `stem_color_G` () : TODO: add description
* `stem_color_B` () : TODO: add description
