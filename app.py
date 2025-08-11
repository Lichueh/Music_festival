from flask import Flask, render_template, request, jsonify
import pandas as pd
import json
import re
from datetime import datetime, date
import os
import glob


app = Flask(__name__)

class MusicFestivalApp:
    def __init__(self):
        self.df = None
        self.load_data()
    
    def load_data(self):
        try:
            json_file = "deduplicated_events.json"
            
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.df = pd.DataFrame(data)
            
            # 處理日期
            processed_dates = []
            for dates_list in self.df['event_dates']:
                if isinstance(dates_list, list) and dates_list:
                    first_date = dates_list[0].get('date') if isinstance(dates_list[0], dict) and 'date' in dates_list[0] else None
                    if first_date:
                        try:
                            processed_dates.append(pd.to_datetime(first_date))
                        except:
                            processed_dates.append(pd.NaT)
                    else:
                        processed_dates.append(pd.NaT)
                else:
                    processed_dates.append(pd.NaT)
            
            self.df['start_date'] = processed_dates
            self.df['performers_str'] = self.df['performers'].apply(
                lambda x: ', '.join(x) if isinstance(x, list) else ''
            )
            
            # 處理地點分類
            self._process_locations()
            
        except Exception as e:
            print(f"載入數據時發生錯誤: {e}")
            self.df = pd.DataFrame()
    
    def _process_locations(self):
        taiwan_cities = [
            '台北', '新北', '桃園', '台中', '台南', '高雄', '基隆', '新竹', 
            '苗栗', '彰化', '南投', '雲林', '嘉義', '屏東', 
            '宜蘭', '花蓮', '台東', '澎湖', '金門', '連江'
        ]
        
        self.df['location_normalized'] = self.df['location'].str.replace('臺', '台') if self.df['location'].dtype == object else self.df['location']
        
        def map_to_city(location):
            if pd.isna(location):
                return '未指定'
            
            location = str(location).strip()
            
            # 定義無效地點列表
            invalid_locations = [
                '未知', '其他地區', '待定', '酒吧', '南壩天',
                '遼寧省瀋陽市', '昆明', '南京', '山東省棗莊市', 
                '澳門站、香港站', '北京', '重庆', '烟台养马岛',
                'Mira Place', '江蘇省常州市', '湖州', '淮安龙宫',
                '安徽阜陽', '寧波市', '吉隆坡', '安徽合肥',
                '瀋陽', '江蘇揚州', '濟宁體育中心', '觀塘海濱公園',
                '河北張北', '橫店影視城', '佛山', '汕頭superlive'
            ]
            
            # 檢查是否為無效地點
            for invalid in invalid_locations:
                if invalid in location:
                    return None  # 返回None表示應該被過濾掉
            
            # 台灣城市關鍵字對應
            city_keywords = {
                '台北': ['台北', '臺北', '北市', '大台北'],
                '新北': ['新北', '新莊', '板橋', '三重', '中和', '永和', '土城', '樹林', '鶯歌', '三峽', '淡水', '汐止', '貢寮'],
                '桃園': ['桃園', '中壢'],
                '台中': ['台中', '臺中', '中市', '豐原', '后里', '烏日'],
                '台南': ['台南', '臺南', '南市', '將軍'],
                '高雄': ['高雄', '鳳山'],
                '基隆': ['基隆'],
                '新竹': ['新竹', '竹北'],
                '苗栗': ['苗栗', '後龍'],
                '彰化': ['彰化', '鹿港'],
                '南投': ['南投', '埔里', '車埕'],
                '雲林': ['雲林'],
                '嘉義': ['嘉義'],
                '屏東': ['屏東', '墾丁'],
                '宜蘭': ['宜蘭'],
                '花蓮': ['花蓮'],
                '台東': ['台東', '臺東', '鹿野'],
                '澎湖': ['澎湖'],
                '金門': ['金門'],
                '連江': ['連江', '馬祖']
            }
            
            # 尋找匹配的城市
            for city, keywords in city_keywords.items():
                for keyword in keywords:
                    if keyword in location:
                        return city
            
            # 如果都沒有匹配到明確的城市，統一視為無效地點
            # 不再保留"其他台灣地區"，只保留能明確分類的城市
            return None
        
        self.df['city'] = self.df['location_normalized'].apply(map_to_city)
        
        # 過濾掉城市為None的行（無效地點）
        self.df = self.df[self.df['city'].notna()]
    
    def filter_events(self, filters):
        df_filtered = self.df.copy()
        
        # 日期過濾
        if filters.get('start_date') and filters.get('end_date'):
            try:
                start_date = pd.to_datetime(filters['start_date'])
                end_date = pd.to_datetime(filters['end_date'])
                mask = (df_filtered['start_date'] >= start_date) & (df_filtered['start_date'] <= end_date)
                df_filtered = df_filtered[mask]
            except:
                pass
        
        # 城市過濾
        if filters.get('cities'):
            cities = filters['cities'] if isinstance(filters['cities'], list) else [filters['cities']]
            df_filtered = df_filtered[df_filtered['city'].isin(cities)]
        
        # 演出者搜索
        if filters.get('search_term'):
            search_term = filters['search_term']
            df_filtered = df_filtered[
                df_filtered['performers_str'].str.contains(
                    f"\\b{re.escape(search_term)}\\b", 
                    case=False, 
                    regex=True, 
                    na=False
                )
            ]
        
        # 活動名稱搜索
        if filters.get('event_name_search'):
            event_name_search = filters['event_name_search']
            df_filtered = df_filtered[
                df_filtered['event_name'].str.contains(
                    re.escape(event_name_search), 
                    case=False, 
                    regex=True, 
                    na=False
                )
            ]
        
        # 排序
        sort_option = filters.get('sort', 'date_asc')
        if sort_option == 'date_asc':
            df_filtered = df_filtered.sort_values('start_date')
        elif sort_option == 'date_desc':
            df_filtered = df_filtered.sort_values('start_date', ascending=False)
        elif sort_option == 'name_asc':
            df_filtered = df_filtered.sort_values('event_name')
        elif sort_option == 'name_desc':
            df_filtered = df_filtered.sort_values('event_name', ascending=False)
        
        return df_filtered
    
    def get_city_stats(self, df_filtered=None):
        if df_filtered is None:
            df_filtered = self.df
        return df_filtered['city'].value_counts().to_dict()
    
    def get_available_cities(self):
        return sorted(self.df['city'].unique().tolist())
    
    def get_date_range(self):
        valid_dates = [d for d in self.df['start_date'] if not pd.isna(d)]
        if valid_dates:
            return {
                'min_date': min(valid_dates).strftime('%Y-%m-%d'),
                'max_date': max(valid_dates).strftime('%Y-%m-%d')
            }
        return {'min_date': None, 'max_date': None}
    
    def get_time_series_data(self, df_filtered=None):
        """獲取按時間的活動數量統計"""
        if df_filtered is None:
            df_filtered = self.df
            
        valid_dates = [d for d in df_filtered['start_date'] if not pd.isna(d)]
        if not valid_dates:
            return {}
        
        # 按月份統計
        date_series = pd.Series(valid_dates)
        monthly_counts = date_series.dt.to_period('M').value_counts().sort_index()
        
        return {
            'labels': [str(period) for period in monthly_counts.index],
            'data': monthly_counts.values.tolist()
        }
    
    def get_city_chart_data(self, df_filtered=None):
        """獲取按地區的活動數量統計，適合熱力圖"""
        if df_filtered is None:
            df_filtered = self.df
            
        city_counts = df_filtered['city'].value_counts()
        
        return {
            'labels': city_counts.index.tolist(),
            'data': city_counts.values.tolist()
        }
    
    def extract_filters_from_request(self, request):
        """從request中提取過濾參數的統一方法"""
        return {
            'start_date': request.args.get('start_date'),
            'end_date': request.args.get('end_date'),
            'cities': request.args.getlist('cities'),
            'search_term': request.args.get('search_term'),
            'event_name_search': request.args.get('event_name_search'),
            'sort': request.args.get('sort', 'date_asc')
        }

# 初始化應用
music_app = MusicFestivalApp()

@app.route('/')

def index():
    return render_template('index.html', 
                         cities=music_app.get_available_cities(),
                         date_range=music_app.get_date_range(),
                         date=datetime)


@app.route('/api/events')
def get_events():
    filters = music_app.extract_filters_from_request(request)
    
    df_filtered = music_app.filter_events(filters)
    
    # 轉換為JSON格式
    events = []
    for _, row in df_filtered.iterrows():
        event = {
            'id': int(row.name),
            'event_name': row['event_name'] if not pd.isna(row['event_name']) else "未知活動",
            'location': row['location'] if not pd.isna(row['location']) else "未指定地點",
            'city': row['city'] if not pd.isna(row['city']) else "未分類地區",
            'performers': row['performers'] if isinstance(row['performers'], list) else [],
            'text': row['text'] if not pd.isna(row['text']) else "",
            'post_url': row['post_url'] if not pd.isna(row['post_url']) else "",
            'event_dates': [],
            'ticket_prices': row['ticket_prices'] if isinstance(row['ticket_prices'], list) else []
        }
        
        # 處理日期
        if isinstance(row['event_dates'], list) and row['event_dates']:
            for date_obj in row['event_dates']:
                if isinstance(date_obj, dict) and 'date' in date_obj:
                    try:
                        formatted_date = pd.to_datetime(date_obj['date']).strftime('%Y-%m-%d')
                        event['event_dates'].append(formatted_date)
                    except:
                        pass
        
        events.append(event)
    
    return jsonify({
        'events': events,
        'total_count': len(events),
        'city_stats': music_app.get_city_stats(df_filtered)
    })

@app.route('/api/stats')
def get_stats():
    return jsonify({
        'total_events': len(music_app.df),
        'cities': music_app.get_available_cities(),
        'city_stats': music_app.get_city_stats(),
        'date_range': music_app.get_date_range()
    })

@app.route('/api/charts/city')
def get_city_chart():
    """獲取城市分布圖表數據（基於過濾條件）"""
    # 獲取過濾參數
    filters = music_app.extract_filters_from_request(request)
    
    # 使用過濾後的數據
    df_filtered = music_app.filter_events(filters)
    chart_data = music_app.get_city_chart_data(df_filtered)
    
    return jsonify({
        'chart_data': chart_data,
        'filtered_count': len(df_filtered),
        'total_count': len(music_app.df),
        'filters_applied': any(v for v in filters.values() if v)
    })

@app.route('/api/charts/timeline')
def get_timeline_chart():
    """獲取時間線圖表數據（基於過濾條件）"""
    # 獲取過濾參數
    filters = music_app.extract_filters_from_request(request)
    
    # 使用過濾後的數據
    df_filtered = music_app.filter_events(filters)
    chart_data = music_app.get_time_series_data(df_filtered)
    
    return jsonify({
        'chart_data': chart_data,
        'filtered_count': len(df_filtered),
        'total_count': len(music_app.df),
        'filters_applied': any(v for v in filters.values() if v)
    })

if __name__ == '__main__':
    app.run(debug=True, port=5002)  # 改為5002避免衝突