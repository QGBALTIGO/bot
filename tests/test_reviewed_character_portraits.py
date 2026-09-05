from utils.reviewed_character_portraits import apply_reviewed_portrait, image_source

ROW={'character_id':17,'anime_id':20,'previous_image':'https://old.example/naruto.jpg','image':'https://new.example/naruto.jpg'}

def test_reviewed_image_replaces_matching_effective_baseline():
    ch={'id':17,'anime_id':20,'image':'/api/image-proxy?url=https%3A%2F%2Fold.example%2Fnaruto.jpg'}
    apply_reviewed_portrait(ch,{17:ROW})
    assert ch['image']==ROW['image']

def test_later_manual_image_keeps_priority():
    ch={'id':17,'anime_id':20,'image':'https://admin.example/new.jpg'}
    apply_reviewed_portrait(ch,{17:ROW})
    assert ch['image']=='https://admin.example/new.jpg'

def test_other_franchise_and_unreviewed_character_unchanged():
    ch={'id':17,'anime_id':21,'image':ROW['previous_image']}
    apply_reviewed_portrait(ch,{17:ROW})
    assert ch['image']==ROW['previous_image']
    ch['anime_id']=20
    apply_reviewed_portrait(ch,{})
    assert ch['image']==ROW['previous_image']
