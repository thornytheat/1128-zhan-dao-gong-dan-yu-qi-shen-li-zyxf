from .snapshot import historical_rows,predict_rows

def build_features(permitted,outcomes,clock,config):
    train=historical_rows(outcomes,config["split"],config["at"])
    rows,missing=predict_rows(permitted,clock,config["road_classes"],config["required"],config["at"])
    return train,rows,missing

def feature_check(points,missing):
    return [{"permit":key,"time_fraction":round(point.values[0],4),
             "workload":round(point.values[4],4),"missing":list(missing[key]),"visible":point.visible}
            for key,point in sorted(points.items())]
